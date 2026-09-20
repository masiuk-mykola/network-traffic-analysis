import logging
from collections.abc import AsyncIterator, Iterable

from fastapi.sse import ServerSentEvent

from capture_api.deps import AuthContext
from capture_api.domain.models import DetectionResetEvent, ReauthEvent
from capture_api.platform.chaos import ChaosController
from capture_api.platform.observer import Observer
from capture_api.platform.tokens import TokenStore
from capture_api.realtime.bus import DetectionBus, Subscription
from capture_api.world.clock import TimeSource
from capture_api.world.types import DetectionData, World

log = logging.getLogger(__name__)

TICK_S = 0.05
"""How long a stream waits for the next detection before re-checking its deadlines."""

RETRY_MS = 3_000
"""``retry:`` hint sent on open: clients reconnect no faster than this."""


def resume_point(header: str | None, query: str | None) -> int | None:
    raw = header or query
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        log.debug("ignoring unparseable resume point %r", raw)
        return None
    return max(0, value)


def detection_event(world: World, detection: DetectionData) -> ServerSentEvent:
    return ServerSentEvent(
        id=str(detection.seq),
        event="detection",
        data=world.to_detection(detection),
    )


class DetectionStream:
    def __init__(
        self,
        *,
        bus: DetectionBus,
        world: World,
        tokens: TokenStore,
        chaos: ChaosController,
        observer: Observer,
        auth: AuthContext,
        sensor_ids: Iterable[str],
        resume_from: int | None,
        time_source: TimeSource,
        tick_s: float = TICK_S,
    ) -> None:
        self._bus = bus
        self._world = world
        self._tokens = tokens
        self._observer = observer
        self._auth = auth
        self._sensor_ids = frozenset(sensor_ids)
        self._resume_from = resume_from
        self._time = time_source
        self._tick_s = tick_s
        self._rotate_s = float(chaos.sse_rotate_s)
        self._last_seq = 0
        self._reason = "client"

    @property
    def reason(self) -> str:
        return self._reason

    async def events(self) -> AsyncIterator[ServerSentEvent]:
        head = self._bus.head_seq()
        subscription = self._bus.subscribe(
            family_id=self._auth.family_id, sensor_ids=self._sensor_ids
        )
        self._observer.sse_opened(
            self._auth.family_id, self._auth.user.id, resume_from=self._resume_from
        )
        try:
            yield ServerSentEvent(comment=f"open last_seq={head}", retry=RETRY_MS)
            self._last_seq = head if self._resume_from is None else self._resume_from
            for event in self._resume(head):
                yield event
            async for event in self._live(subscription):
                yield event
        finally:
            self._bus.release(subscription, self._reason)
            self._observer.sse_closed(self._auth.family_id, self._auth.user.id, reason=self._reason)

    def _resume(self, head: int) -> list[ServerSentEvent]:
        if self._resume_from is None:
            return []
        oldest = self._bus.oldest_seq()
        if oldest and self._resume_from < oldest - 1:
            self._last_seq = head
            return [
                ServerSentEvent(
                    event="reset",
                    data=DetectionResetEvent(
                        reason="resume_point_too_old", oldest_seq=oldest, last_seq=head
                    ),
                )
            ]
        replayed = self._bus.replay(self._resume_from, self._sensor_ids)
        if replayed:
            self._last_seq = max(self._last_seq, replayed[-1].seq)
        return [detection_event(self._world, detection) for detection in replayed]

    async def _live(self, subscription: Subscription) -> AsyncIterator[ServerSentEvent]:
        deadline = self._time.monotonic() + self._rotate_s
        while True:
            if subscription.closed:
                self._reason = "revoked"
                return
            if self._token_expired():
                self._reason = "reauth"
                yield ServerSentEvent(event="reauth", data=ReauthEvent(reason="token_expired"))
                return
            if self._time.monotonic() >= deadline:
                self._reason = "rotate"
                return
            detection = await subscription.next(self._tick_s)
            if detection is None or detection.seq <= self._last_seq:
                continue
            self._last_seq = detection.seq
            yield detection_event(self._world, detection)

    def _token_expired(self) -> bool:
        remaining = self._tokens.access_remaining_s(self._auth.token)
        return remaining is None or remaining <= 0
