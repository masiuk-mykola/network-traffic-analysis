import asyncio
import json
import logging
import secrets
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any, cast

from fastapi import Depends, WebSocket
from pydantic import TypeAdapter, ValidationError
from starlette.requests import HTTPConnection
from starlette.websockets import WebSocketDisconnect, WebSocketState

from capture_api.domain.base import WireModel, from_epoch_ms
from capture_api.domain.models import (
    LiveAck,
    LiveClientFrame,
    LiveError,
    LiveHello,
    LiveLagging,
    LivePause,
    LivePing,
    LivePong,
    LiveProtocolStats,
    LiveResume,
    LiveSearchProgress,
    LiveSessionFrame,
    LiveStats,
    LiveSubscribe,
    LiveWatchSearch,
    RootFilter,
    Search,
    SearchProgress,
    SearchState,
)
from capture_api.platform.chaos import ChaosController
from capture_api.platform.observer import Observer
from capture_api.platform.permissions import User, can_read_sensor
from capture_api.platform.tokens import RevokeReason, TokenStore
from capture_api.world.clock import TimeSource
from capture_api.world.types import Row, World

log = logging.getLogger(__name__)

TICKET_PREFIX = "lt_"
TICKET_CHARS = 32
TICKET_TTL_S = 30.0

TICK_S = 0.05
HEARTBEAT_S = 15.0
PONG_DEADLINE_S = 10.0
STATS_INTERVAL_S = 1.0
SEND_QUEUE_LIMIT = 500
"""Outbound frames buffered before session frames start being dropped (a ``lagging`` frame)."""

CLOSE_TICKET = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_PONG = 4408
CLOSE_RESTART = 1013
CLOSE_NORMAL = 1000

_CLIENT_FRAMES: TypeAdapter[LiveClientFrame] = TypeAdapter(LiveClientFrame)


@dataclass(slots=True)
class Ticket:
    ticket: str
    family_id: str
    user: User
    sensor_ids: tuple[str, ...]
    expires_at: float
    used: bool = False


@dataclass(slots=True)
class Subscription:
    sub_id: str
    generation: int
    sensor_ids: tuple[str, ...]
    channels: frozenset[str]
    matches: Callable[[Row], bool]
    cursors: dict[str, tuple[int, int]] = field(default_factory=dict)


class LiveService:
    def __init__(
        self, *, tokens: TokenStore, time_source: TimeSource, ttl_s: float = TICKET_TTL_S
    ) -> None:
        self._tokens = tokens
        self._time = time_source
        self._ttl_s = ttl_s
        self._tickets: dict[str, Ticket] = {}
        self._sockets: set[LiveSocket] = set()

    @property
    def ttl_s(self) -> float:
        return self._ttl_s

    def issue(self, *, family_id: str, user: User, sensor_ids: Iterable[str]) -> Ticket:
        self._sweep()
        ticket = Ticket(
            ticket=TICKET_PREFIX + secrets.token_urlsafe(TICKET_CHARS)[:TICKET_CHARS],
            family_id=family_id,
            user=user,
            sensor_ids=tuple(sensor_ids),
            expires_at=self._time.monotonic() + self._ttl_s,
        )
        self._tickets[ticket.ticket] = ticket
        return ticket

    def redeem(self, presented: str | None) -> tuple[Ticket | None, str]:
        if not presented:
            return None, "ticket_missing"
        ticket = self._tickets.get(presented)
        if ticket is None:
            return None, "ticket_invalid"
        if ticket.used:
            return None, "ticket_reuse"
        if self._time.monotonic() >= ticket.expires_at:
            return None, "ticket_expired"
        family = self._tokens.family(ticket.family_id)
        if family is None or family.revoked:
            return None, "session_revoked"
        ticket.used = True
        return ticket, "ok"

    def family_of(self, presented: str | None) -> str | None:
        ticket = self._tickets.get(presented or "")
        return None if ticket is None else ticket.family_id

    def _sweep(self) -> None:
        now = self._time.monotonic()
        for key, ticket in list(self._tickets.items()):
            if ticket.used or now >= ticket.expires_at:
                del self._tickets[key]

    def register(self, socket: "LiveSocket") -> None:
        self._sockets.add(socket)

    def unregister(self, socket: "LiveSocket") -> None:
        self._sockets.discard(socket)

    def close_family(self, family_id: str, code: int = CLOSE_NORMAL) -> int:
        doomed = [s for s in self._sockets if s.family_id == family_id]
        for socket in doomed:
            socket.request_close(code, "revoked")
        return len(doomed)

    def close_all(self, code: int, reason: str) -> None:
        for socket in list(self._sockets):
            socket.request_close(code, reason)

    def count(self) -> int:
        return len(self._sockets)

    def reset(self) -> None:
        self._tickets.clear()
        self.close_all(CLOSE_RESTART, "reset")


def get_live(conn: HTTPConnection) -> LiveService:
    return cast(LiveService, conn.app.state.live)


LiveDep = Annotated[LiveService, Depends(get_live)]


def compile_filter(world: World, node: RootFilter | None) -> Callable[[Row], bool] | None:
    if node is None:
        return lambda _row: True
    try:
        from capture_api.search.compile import compile_for_world  # noqa: PLC0415
    except ModuleNotFoundError:
        log.warning("no filter compiler yet; the live subscription matches every row")
        return lambda _row: True
    try:
        return compile_for_world(node, world)
    except Exception:
        log.debug("live subscription filter rejected", exc_info=True)
        return None


def search_progress(state: Any, search_id: str) -> LiveSearchProgress | None:
    job = _peek(state, search_id)
    if job is None:
        return None
    view = _search_view(job)
    if view is None:
        return None
    return LiveSearchProgress(search_id=search_id, state=view[0], progress=view[1])


def _peek(state: Any, search_id: str) -> Any | None:
    service = getattr(state, "searches", None)
    for name in ("peek", "view", "snapshot", "find"):
        lookup = getattr(service, name, None)
        if not callable(lookup):
            continue
        try:
            found = lookup(search_id)
        except Exception:
            log.debug("search lookup %s(%r) failed", name, search_id, exc_info=True)
            continue
        return found
    return None


def _search_view(job: Any) -> tuple[SearchState, SearchProgress] | None:
    state = getattr(job, "state", None)
    progress = getattr(job, "progress", None)
    if progress is None:
        model = _as_model(job)
        return None if model is None else (model.state, model.progress)
    if not isinstance(progress, SearchProgress):
        try:
            progress = SearchProgress.model_validate(progress)
        except ValidationError:
            return None
    if state is None:
        return None
    return (cast(SearchState, str(state)), progress)


def _as_model(job: Any) -> Search | None:
    try:
        from capture_api.search.jobs import to_model  # noqa: PLC0415
    except ModuleNotFoundError:
        return None
    try:
        return to_model(job)
    except Exception:
        log.debug("search job could not be rendered", exc_info=True)
        return None


class LiveSocket:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        ticket: Ticket,
        world: World,
        chaos: ChaosController,
        observer: Observer,
        tokens: TokenStore,
        live: LiveService,
        time_source: TimeSource,
        tick_s: float = TICK_S,
    ) -> None:
        self._ws = websocket
        self._ticket = ticket
        self._world = world
        self._chaos = chaos
        self._observer = observer
        self._tokens = tokens
        self._live = live
        self._time = time_source
        self._tick_s = tick_s
        self._queue: deque[str] = deque()
        self._subscription: Subscription | None = None
        self._paused = False
        self._generation = 0
        self._seq = 0
        self._sent = 0
        self._dropped = 0
        self._stats: dict[str, LiveProtocolStats] = {}
        self._watched: dict[str, tuple[str, float, int]] = {}
        self._close_code: int | None = None
        self._close_reason = "client"
        self._disconnected = False
        self._ping_nonce: str | None = None
        self._pong_deadline = 0.0
        now = time_source.monotonic()
        self._opened_at = now
        self._next_ping = now + HEARTBEAT_S
        self._next_stats = now + STATS_INTERVAL_S
        self._unsubscribe: Callable[[], None] = lambda: None

    @property
    def family_id(self) -> str:
        return self._ticket.family_id

    def request_close(self, code: int, reason: str) -> None:
        if self._close_code is None:
            self._close_code = code
            self._close_reason = reason

    async def run(self) -> None:
        user = self._ticket.user
        self._observer.ws_opened(self.family_id, user.id)
        self._unsubscribe = self._tokens.on_family_revoked(self.family_id, self._on_revoked)
        self._live.register(self)
        self._send(
            LiveHello(server_time=self._world.clock.now(), heartbeat_s=int(HEARTBEAT_S)),
            droppable=False,
        )
        receiver = asyncio.create_task(self._receive_loop(), name="live-receive")
        sender = asyncio.create_task(self._send_loop(), name="live-send")
        try:
            await self._produce_loop()
        finally:
            await self._shutdown(receiver, sender)

    async def _shutdown(self, *tasks: asyncio.Task[None]) -> None:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                log.debug("live socket task cancelled")
        self._unsubscribe()
        self._live.unregister(self)
        code = self._close_code or CLOSE_NORMAL
        if not self._disconnected:
            try:
                await self._ws.close(code)
            except RuntimeError:
                log.debug("live socket already closed")
        self._observer.ws_closed(
            self.family_id, self._ticket.user.id, code=code, reason=self._close_reason
        )

    def _on_revoked(self, _family_id: str, reason: RevokeReason) -> None:
        self.request_close(CLOSE_NORMAL, f"revoked:{reason}")

    def _send(self, frame: WireModel, *, droppable: bool) -> None:
        if droppable and len(self._queue) >= SEND_QUEUE_LIMIT:
            self._dropped += 1
            return
        self._queue.append(frame.model_dump_json())
        self._sent += 1

    async def _send_loop(self) -> None:
        while True:
            if not self._queue:
                await asyncio.sleep(self._tick_s)
                continue
            text = self._queue.popleft()
            try:
                await self._ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError):
                self._disconnected = True
                return

    async def _receive_loop(self) -> None:
        while True:
            try:
                message = await self._ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                self._disconnected = True
                return
            if message["type"] == "websocket.disconnect":
                self._disconnected = True
                return
            self._handle(message.get("text") or _decode(message.get("bytes")))

    def _handle(self, text: str | None) -> None:
        if text is None:
            self._error("bad_frame", "Expected a JSON text frame.")
            return
        try:
            frame = _CLIENT_FRAMES.validate_python(json.loads(text))
        except (ValidationError, json.JSONDecodeError, TypeError):
            self._error("bad_frame", "Unknown or malformed client frame.")
            return
        self._dispatch(frame)

    def _dispatch(self, frame: LiveClientFrame) -> None:
        if isinstance(frame, LiveSubscribe):
            self._on_subscribe(frame)
        elif isinstance(frame, LivePause):
            self._paused = True
        elif isinstance(frame, LiveResume):
            self._paused = False
        elif isinstance(frame, LivePong):
            self._on_pong(frame.nonce)
        elif isinstance(frame, LiveWatchSearch):
            self._on_watch(frame.search_id)
        else:
            self._watched.pop(frame.search_id, None)

    def _error(self, code: str, message: str) -> None:
        self._send(LiveError(code=code, message=message), droppable=False)

    def _on_subscribe(self, frame: LiveSubscribe) -> None:
        for sensor_id in frame.sensor_ids:
            if sensor_id not in self._ticket.sensor_ids or not can_read_sensor(
                self._ticket.user.role, sensor_id
            ):
                self.request_close(CLOSE_FORBIDDEN, f"sensor:{sensor_id}")
                return
        matches = compile_filter(self._world, frame.filter)
        if matches is None:
            self._error("bad_filter", "The subscription filter is not valid.")
            return
        self._generation += 1
        self._subscription = Subscription(
            sub_id=frame.sub_id,
            generation=self._generation,
            sensor_ids=tuple(frame.sensor_ids),
            channels=frozenset(frame.channels),
            matches=matches,
            cursors={sensor: self._start_cursor(sensor) for sensor in frame.sensor_ids},
        )
        self._paused = False
        self._stats.clear()
        self._observer.ws_subscribed(self.family_id, self._ticket.user.id)
        self._send(LiveAck(sub_id=frame.sub_id, generation=self._generation), droppable=False)

    def _start_cursor(self, sensor_id: str) -> tuple[int, int]:
        return (self._world.visible_until_ms(sensor_id), 1 << 63)

    def _on_pong(self, nonce: str) -> None:
        if self._ping_nonce is None or nonce != self._ping_nonce:
            self._error("bad_nonce", "This pong does not answer the outstanding ping.")
            return
        self._ping_nonce = None
        self._pong_deadline = 0.0
        self._observer.ws_pong(self.family_id, self._ticket.user.id)

    def _on_watch(self, search_id: str) -> None:
        frame = search_progress(self._ws.app.state, search_id)
        if frame is None:
            self._error("search_not_found", f"No search {search_id} to watch.")
            return
        self._watched[search_id] = _progress_key(frame)
        self._send(frame, droppable=False)

    async def _produce_loop(self) -> None:
        while self._close_code is None and not self._disconnected:
            self._tick_sessions()
            self._tick_periodic()
            self._tick_ping()
            self._tick_restart()
            await asyncio.sleep(self._tick_s)

    def _tick_sessions(self) -> None:
        subscription = self._subscription
        if subscription is None or self._paused:
            return
        until_ms = self._world.capture_now_ms() + 1
        for sensor_id in subscription.sensor_ids:
            cursor = subscription.cursors.get(sensor_id, (until_ms, 1 << 63))
            newest = cursor
            for row in self._world.rows(sensor_id, cursor[0], until_ms):
                key = (row.start_ms, row.id)
                if key <= cursor:
                    continue
                newest = max(newest, key)
                self._release(subscription, row)
            subscription.cursors[sensor_id] = newest

    def _release(self, subscription: Subscription, row: Row) -> None:
        if not subscription.matches(row):
            return
        self._count(row)
        if "sessions" not in subscription.channels:
            return
        self._session_frame(subscription, row, synthetic=False)
        for _ in range(self._chaos.live_burst):
            self._session_frame(subscription, row, synthetic=True)

    def _session_frame(self, subscription: Subscription, row: Row, *, synthetic: bool) -> None:
        self._seq += 1
        self._send(
            LiveSessionFrame(
                generation=subscription.generation,
                seq=self._seq,
                row=self._world.to_session_row(row),
                synthetic=True if synthetic else None,
            ),
            droppable=True,
        )

    def _count(self, row: Row) -> None:
        current = self._stats.get(row.protocol)
        sessions = 1 if current is None else current.sessions + 1
        total = row.bytes_up + row.bytes_down + (0 if current is None else current.bytes)
        self._stats[row.protocol] = LiveProtocolStats(sessions=sessions, bytes=total)

    def _tick_periodic(self) -> None:
        now = self._time.monotonic()
        if now < self._next_stats:
            return
        self._next_stats = now + STATS_INTERVAL_S
        subscription = self._subscription
        if subscription is not None and "stats" in subscription.channels:
            self._send(
                LiveStats(
                    generation=subscription.generation,
                    t=from_epoch_ms(self._world.capture_now_ms()),
                    by_protocol=dict(self._stats),
                ),
                droppable=False,
            )
            self._stats.clear()
        self._tick_lagging(subscription)
        self._tick_watched()

    def _tick_lagging(self, subscription: Subscription | None) -> None:
        if not self._dropped:
            return
        total = self._sent + self._dropped
        self._send(
            LiveLagging(
                generation=subscription.generation if subscription else self._generation,
                dropped=self._dropped,
                sample_rate=round(self._sent / total, 4) if total else 0.0,
            ),
            droppable=False,
        )
        self._dropped = 0
        self._sent = 0

    def _tick_watched(self) -> None:
        for search_id, seen in list(self._watched.items()):
            frame = search_progress(self._ws.app.state, search_id)
            if frame is None or _progress_key(frame) == seen:
                continue
            self._watched[search_id] = _progress_key(frame)
            self._send(frame, droppable=False)

    def _tick_ping(self) -> None:
        now = self._time.monotonic()
        if self._ping_nonce is not None and now >= self._pong_deadline:
            self.request_close(CLOSE_PONG, "missed_pong")
            return
        if now < self._next_ping or self._ping_nonce is not None:
            return
        self._ping_nonce = secrets.token_hex(8)
        self._next_ping = now + HEARTBEAT_S
        self._pong_deadline = now + PONG_DEADLINE_S
        self._send(LivePing(nonce=self._ping_nonce), droppable=False)

    def _tick_restart(self) -> None:
        restart_s = self._chaos.ws_restart_s
        if restart_s is not None and self._time.monotonic() - self._opened_at >= restart_s:
            self.request_close(CLOSE_RESTART, "server_restart")


def _decode(payload: bytes | None) -> str | None:
    if payload is None:
        return None
    try:
        return payload.decode()
    except UnicodeDecodeError:
        return None


def _progress_key(frame: LiveSearchProgress) -> tuple[str, float, int]:
    return (frame.state, frame.progress.percent, frame.progress.matched)


async def serve(
    websocket: WebSocket,
    *,
    ticket: str | None,
    allowed_origins: Iterable[str],
    live: LiveService,
    world: World,
    chaos: ChaosController,
    observer: Observer,
    tokens: TokenStore,
    time_source: TimeSource,
) -> None:
    origin = websocket.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in set(allowed_origins):
        observer.ws_rejected(live.family_of(ticket), "origin", code=CLOSE_FORBIDDEN)
        await _refuse(websocket, CLOSE_FORBIDDEN)
        return
    granted, reason = live.redeem(ticket)
    if granted is None:
        observer.ws_rejected(live.family_of(ticket), reason, code=CLOSE_TICKET)
        await _refuse(websocket, CLOSE_TICKET)
        return
    await websocket.accept()
    socket = LiveSocket(
        websocket,
        ticket=granted,
        world=world,
        chaos=chaos,
        observer=observer,
        tokens=tokens,
        live=live,
        time_source=time_source,
    )
    await socket.run()


async def _refuse(websocket: WebSocket, code: int) -> None:
    await websocket.accept()
    if websocket.client_state is not WebSocketState.DISCONNECTED:
        await websocket.close(code)
