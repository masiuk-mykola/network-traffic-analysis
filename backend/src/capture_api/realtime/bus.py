import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from typing import Annotated, cast

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection

from capture_api.platform.chaos import ChaosController
from capture_api.platform.tokens import RevokeReason, TokenStore
from capture_api.world.types import DetectionData, World

log = logging.getLogger(__name__)

RING_SIZE = 1_000
"""How many released detections stay replayable through ``Last-Event-ID``."""

QUEUE_SIZE = 1_000
"""Per-subscriber backlog; a subscriber that stops reading loses its oldest events."""

POLL_INTERVAL_S = 0.1
"""How often the pump asks the world for newly released detections."""


class Subscription:
    __slots__ = (
        "_items",
        "_wakeup",
        "close_reason",
        "closed",
        "dropped",
        "family_id",
        "sensor_ids",
    )

    def __init__(self, family_id: str, sensor_ids: frozenset[str]) -> None:
        self.family_id = family_id
        self.sensor_ids = sensor_ids
        self.closed = False
        self.close_reason: str | None = None
        self.dropped = 0
        self._items: deque[DetectionData] = deque(maxlen=QUEUE_SIZE)
        self._wakeup = asyncio.Event()

    def wants(self, detection: DetectionData) -> bool:
        return detection.sensor_id in self.sensor_ids

    def push(self, detection: DetectionData) -> None:
        if self.closed or not self.wants(detection):
            return
        if len(self._items) == QUEUE_SIZE:
            self.dropped += 1
        self._items.append(detection)
        self._wakeup.set()

    def close(self, reason: str) -> None:
        if self.closed:
            return
        self.closed = True
        self.close_reason = reason
        self._wakeup.set()

    async def next(self, timeout: float) -> DetectionData | None:
        if not self._items and not self.closed:
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout)
            except TimeoutError:
                return None
        self._wakeup.clear()
        item = self._items.popleft() if self._items else None
        if self._items or self.closed:
            self._wakeup.set()
        return item


class DetectionBus:
    def __init__(
        self,
        *,
        world: Callable[[], World | None],
        tokens: TokenStore,
        poll_interval_s: float = POLL_INTERVAL_S,
        ring_size: int = RING_SIZE,
    ) -> None:
        self._world = world
        self._tokens = tokens
        self._poll_interval_s = poll_interval_s
        self._ring_size = ring_size
        self._ring: deque[DetectionData] = deque(maxlen=ring_size)
        self._cursor = 0
        self._primed = False
        self._active = False
        self._subscriptions: set[Subscription] = set()
        self._unsubscribe: dict[str, Callable[[], None]] = {}
        self._reset_hooks: list[Callable[[], None]] = []

    def activate(self) -> None:
        self._active = True

    def refresh(self) -> Sequence[DetectionData]:
        world = self._world()
        if world is None:
            return ()
        self._active = True
        now_ms = world.capture_now_ms()
        if not self._primed:
            self._prime(world.detections_until(now_ms))
            return ()
        fresh = world.detections_after(self._cursor, now_ms)
        if not fresh:
            return ()
        self._cursor = fresh[-1].seq
        for detection in fresh:
            self._ring.append(detection)
            for subscription in self._subscriptions:
                subscription.push(detection)
        return fresh

    def _prime(self, released: Sequence[DetectionData]) -> None:
        self._primed = True
        self._ring.extend(released[-self._ring_size :])
        self._cursor = released[-1].seq if released else 0

    def head_seq(self) -> int:
        self.refresh()
        return self._cursor

    def oldest_seq(self) -> int:
        self.refresh()
        return self._ring[0].seq if self._ring else 0

    def replay(self, after_seq: int, sensor_ids: Iterable[str]) -> list[DetectionData]:
        wanted = frozenset(sensor_ids)
        return [d for d in self._ring if d.seq > after_seq and d.sensor_id in wanted]

    def backfill(
        self, *, after_seq: int | None, limit: int, sensor_ids: Iterable[str]
    ) -> tuple[list[DetectionData], int]:
        world = self._world()
        if world is None:
            return [], 0
        self.refresh()
        wanted = frozenset(sensor_ids)
        now_ms = world.capture_now_ms()
        released = world.detections_until(now_ms)
        head = released[-1].seq if released else 0
        if after_seq is None:
            matching = [d for d in released if d.sensor_id in wanted][-limit:]
        else:
            matching = [
                d for d in world.detections_after(after_seq, now_ms) if d.sensor_id in wanted
            ][:limit]
        return matching, head

    def subscribe(self, *, family_id: str, sensor_ids: Iterable[str]) -> Subscription:
        subscription = Subscription(family_id, frozenset(sensor_ids))
        self._subscriptions.add(subscription)
        self.refresh()
        if family_id not in self._unsubscribe:
            self._unsubscribe[family_id] = self._tokens.on_family_revoked(
                family_id, self._family_revoked
            )
        return subscription

    def release(self, subscription: Subscription, reason: str = "client") -> None:
        subscription.close(reason)
        self._subscriptions.discard(subscription)
        self._forget_family(subscription.family_id)

    def _forget_family(self, family_id: str) -> None:
        if any(s.family_id == family_id for s in self._subscriptions):
            return
        unsubscribe = self._unsubscribe.pop(family_id, None)
        if unsubscribe is not None:
            unsubscribe()

    def _family_revoked(self, family_id: str, reason: RevokeReason) -> None:
        self.close_family(family_id, f"revoked:{reason}")

    def close_family(self, family_id: str, reason: str = "revoked") -> int:
        doomed = [s for s in self._subscriptions if s.family_id == family_id]
        for subscription in doomed:
            subscription.close(reason)
            self._subscriptions.discard(subscription)
        self._unsubscribe.pop(family_id, None)
        return len(doomed)

    def close_all(self, reason: str) -> None:
        for subscription in list(self._subscriptions):
            subscription.close(reason)
        self._subscriptions.clear()
        for unsubscribe in self._unsubscribe.values():
            unsubscribe()
        self._unsubscribe.clear()

    def count(self) -> int:
        return len(self._subscriptions)

    def add_reset_hook(self, hook: Callable[[], None]) -> None:
        self._reset_hooks.append(hook)

    def reset(self) -> None:
        self.close_all("reset")
        self._ring.clear()
        self._cursor = 0
        self._primed = False
        self._active = False
        for hook in self._reset_hooks:
            hook()

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval_s)
            if not self._active:
                continue
            try:
                self.refresh()
            except Exception:
                log.exception("detection bus pump failed")


def get_bus(conn: HTTPConnection) -> DetectionBus:
    return cast(DetectionBus, conn.app.state.bus)


def get_chaos(conn: HTTPConnection) -> ChaosController:
    return cast(ChaosController, conn.app.state.chaos)


BusDep = Annotated[DetectionBus, Depends(get_bus)]
ChaosDep = Annotated[ChaosController, Depends(get_chaos)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from capture_api.realtime.ws import LiveService  # noqa: PLC0415 - avoids a cycle

    tokens = cast(TokenStore, app.state.tokens)
    bus = DetectionBus(world=lambda: getattr(app.state, "world", None), tokens=tokens)
    live = LiveService(tokens=tokens, time_source=app.state.time)
    bus.add_reset_hook(live.reset)
    app.state.bus = bus
    app.state.live = live
    pump = asyncio.create_task(bus.run(), name="detection-bus")
    try:
        yield
    finally:
        pump.cancel()
        with suppress(asyncio.CancelledError):
            await pump
        live.close_all(1013, "shutdown")
        bus.close_all("shutdown")
