import hashlib
import json
import logging
from collections import deque
from collections.abc import Iterable, Mapping, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from capture_api.domain.base import iso_ms
from capture_api.platform.chaos import Identity, client_key, resolve_identity
from capture_api.platform.tokens import TokenStore
from capture_api.world.clock import TimeSource

log = logging.getLogger(__name__)

type StreamEventKind = Literal[
    "sse_open", "sse_close", "ws_open", "ws_close", "ws_pong", "ws_subscribe", "ws_rejected"
]

ANONYMOUS = "anonymous"
RING_SIZE = 10_000
MAX_REQUEST_BODY = 64 * 1024
MAX_RESPONSE_BODY = 8 * 1024
MAX_QUERY_CHARS = 512

AUTH_PATHS: frozenset[str] = frozenset({"/v1/auth/login", "/v1/auth/refresh"})
RESOURCE_PREFIXES: tuple[str, ...] = ("/v1/hunts", "/v1/cases", "/v1/searches")
DOWNLOAD_SUFFIXES: tuple[str, ...] = ("/pcap", "/file")

_ID_PREFIXES: tuple[str, ...] = ("srch_", "hnt_", "exp_", "imp_", "lt_", "CASE-", "det_", "f_")


def _short_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _query_hash(query: str) -> str:
    return hashlib.sha256("&".join(sorted(query.split("&"))).encode()).hexdigest()[:12]


def _looks_like_id(segment: str) -> bool:
    return (
        segment.isdigit()
        or segment.startswith(_ID_PREFIXES)
        or (len(segment) >= 16 and "." not in segment)
        or ":" in segment
    )


def route_template(scope: Scope, path: str) -> str:
    params = scope.get("path_params") or {}
    if isinstance(params, Mapping) and params:
        template = path
        for name, value in params.items():
            text = str(value)
            if text and text in template:
                template = template.replace(text, f"{{{name}}}")
        return template
    parts = [("{id}" if _looks_like_id(part) else part) for part in path.split("/")]
    return "/".join(parts)


@dataclass(frozen=True, slots=True)
class RequestRecord:
    seq: int
    t_mono: float
    t_iso: str
    family_id: str
    user: str
    method: str
    route: str
    path: str
    query: str
    query_hash: str
    status: int
    duration_ms: float
    has_authorization: bool
    origin: str | None = None
    idempotency_key: str | None = None
    if_match: str | None = None
    last_event_id: str | None = None
    replayed: bool = False
    error_code: str | None = None
    resource_id: str | None = None
    body_keys: tuple[str, ...] = ()
    body_fields: Mapping[str, str] = field(default_factory=dict)
    resource_fields: Mapping[str, str] = field(default_factory=dict)
    body_hash: str | None = None
    retry_after_s: float | None = None
    limit_param: int | None = None
    dropped: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.method, self.path, self.query_hash)


@dataclass(frozen=True, slots=True)
class StreamRecord:
    seq: int
    t_mono: float
    t_iso: str
    family_id: str
    user: str
    kind: StreamEventKind
    resume_from: int | None = None
    code: int | None = None
    reason: str | None = None


@dataclass(slots=True)
class FamilyLog:
    family_id: str
    user: str
    requests: deque[RequestRecord]
    streams: deque[StreamRecord]

    @property
    def request_count(self) -> int:
        return len(self.requests)


class Observer:
    def __init__(
        self,
        time_source: TimeSource,
        *,
        seed: str = "demo",
        full_history: bool = False,
        ring_size: int = RING_SIZE,
    ) -> None:
        self._time = time_source
        self._seed = seed
        self._full_history = full_history
        self._ring: int | None = None if full_history else ring_size
        self._families: MutableMapping[str, FamilyLog] = {}
        self._sticky: MutableMapping[str, tuple[str, str]] = {}
        self._seq = 0

    @property
    def seed(self) -> str:
        return self._seed

    @property
    def full_history(self) -> bool:
        return self._full_history

    @property
    def time_source(self) -> TimeSource:
        return self._time

    def _now(self) -> tuple[float, str]:
        return self._time.monotonic(), iso_ms(datetime.fromtimestamp(self._time.time(), tz=UTC))

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _log(self, family_id: str, user: str) -> FamilyLog:
        log_entry = self._families.get(family_id)
        if log_entry is None:
            log_entry = FamilyLog(
                family_id=family_id,
                user=user,
                requests=deque(maxlen=self._ring),
                streams=deque(maxlen=self._ring),
            )
            self._families[family_id] = log_entry
        elif user and log_entry.user in ("", ANONYMOUS):
            log_entry.user = user
        return log_entry

    def remember_identity(self, client: str, family_id: str, user: str) -> None:
        if family_id != ANONYMOUS:
            self._sticky[client] = (family_id, user)

    def sticky_identity(self, client: str) -> tuple[str, str]:
        return self._sticky.get(client, (ANONYMOUS, ANONYMOUS))

    def record(self, record: RequestRecord) -> RequestRecord:
        self._log(record.family_id, record.user).requests.append(record)
        return record

    def next_record(self, **fields: Any) -> RequestRecord:
        t_mono, t_iso = self._now()
        fields.setdefault("t_mono", t_mono)
        fields.setdefault("t_iso", t_iso)
        return RequestRecord(seq=self._next_seq(), **fields)

    def _stream_event(
        self,
        kind: StreamEventKind,
        family_id: str | None,
        user: str | None,
        **fields: Any,
    ) -> StreamRecord:
        t_mono, t_iso = self._now()
        record = StreamRecord(
            seq=self._next_seq(),
            t_mono=t_mono,
            t_iso=t_iso,
            family_id=family_id or ANONYMOUS,
            user=user or ANONYMOUS,
            kind=kind,
            **fields,
        )
        self._log(record.family_id, record.user).streams.append(record)
        return record

    def sse_opened(
        self, family_id: str | None, user: str | None = None, *, resume_from: int | None = None
    ) -> StreamRecord:
        return self._stream_event("sse_open", family_id, user, resume_from=resume_from)

    def sse_closed(
        self, family_id: str | None, user: str | None = None, *, reason: str = "rotate"
    ) -> StreamRecord:
        return self._stream_event("sse_close", family_id, user, reason=reason)

    def ws_opened(self, family_id: str | None, user: str | None = None) -> StreamRecord:
        return self._stream_event("ws_open", family_id, user)

    def ws_closed(
        self,
        family_id: str | None,
        user: str | None = None,
        *,
        code: int = 1000,
        reason: str | None = None,
    ) -> StreamRecord:
        return self._stream_event("ws_close", family_id, user, code=code, reason=reason)

    def ws_pong(self, family_id: str | None, user: str | None = None) -> StreamRecord:
        return self._stream_event("ws_pong", family_id, user)

    def ws_subscribed(self, family_id: str | None, user: str | None = None) -> StreamRecord:
        return self._stream_event("ws_subscribe", family_id, user)

    def ws_rejected(self, family_id: str | None, reason: str, *, code: int = 4401) -> StreamRecord:
        return self._stream_event("ws_rejected", family_id, None, code=code, reason=reason)

    def families(self) -> list[FamilyLog]:
        return list(self._families.values())

    def family(self, family_id: str) -> FamilyLog | None:
        return self._families.get(family_id)

    def request_count(self) -> int:
        return sum(len(f.requests) for f in self._families.values())

    def open_stream_counts(self) -> tuple[int, int]:
        sse = ws = 0
        for family_log in self._families.values():
            for event in family_log.streams:
                if event.kind == "sse_open":
                    sse += 1
                elif event.kind == "sse_close":
                    sse -= 1
                elif event.kind == "ws_open":
                    ws += 1
                elif event.kind == "ws_close":
                    ws -= 1
        return max(0, sse), max(0, ws)

    def reset(self) -> None:
        self._families.clear()
        self._sticky.clear()
        self._seq = 0


def _headers(scope: Scope) -> dict[str, str]:
    return {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in scope.get("headers", ())
    }


def _retry_after_seconds(raw: str | None, now_wall: float) -> float | None:
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime  # noqa: PLC0415 - rare path

    try:
        return max(0.0, parsedate_to_datetime(raw).timestamp() - now_wall)
    except (TypeError, ValueError):
        return None


def _limit_param(query: str) -> int | None:
    for name, value in parse_qsl(query, keep_blank_values=True):
        if name == "limit":
            try:
                return int(value)
            except ValueError:
                return None
    return None


def _json_object(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _field_hashes(payload: Mapping[str, Any]) -> dict[str, str]:
    return {key: _short_hash(value) for key, value in payload.items()}


def _should_capture_response(path: str, status: int, headers: Mapping[str, str]) -> bool:
    content_type = headers.get("content-type", "")
    if "json" not in content_type:
        return False
    length = headers.get("content-length")
    if length is None or not length.isdigit() or int(length) > MAX_RESPONSE_BODY:
        return False
    return (
        status >= 400
        or path in AUTH_PATHS
        or path.startswith(RESOURCE_PREFIXES)
        or path.startswith("/v1/imports")
    )


class ObserverMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = getattr(scope.get("app"), "state", None)
        observer = cast(Observer | None, getattr(state, "observer", None))
        if observer is None:
            await self.app(scope, receive, send)
            return
        await self._observe(observer, scope, receive, send)

    async def _observe(
        self, observer: Observer, scope: Scope, receive: Receive, send: Send
    ) -> None:
        method = cast(str, scope.get("method", "GET"))
        path = cast(str, scope["path"])
        headers = _headers(scope)
        started = observer.time_source.monotonic()

        request_body = bytearray()
        capture_request = method == "PATCH" or (method == "POST" and path == "/v1/searches")

        async def receive_wrapper() -> Message:
            message = await receive()
            if (
                capture_request
                and message["type"] == "http.request"
                and len(request_body) < MAX_REQUEST_BODY
            ):
                request_body.extend(cast(bytes, message.get("body", b"")))
            return message

        status = 0
        response_headers: dict[str, str] = {}
        response_body = bytearray()
        capture_response = False
        template = ""

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_headers, capture_response, template
            if message["type"] == "http.response.start":
                status = cast(int, message["status"])
                template = route_template(scope, path)
                response_headers = {
                    name.decode("latin-1").lower(): value.decode("latin-1")
                    for name, value in message.get("headers", ())
                }
                capture_response = _should_capture_response(path, status, response_headers)
            elif message["type"] == "http.response.body" and capture_response:
                response_body.extend(cast(bytes, message.get("body", b"")))
                if len(response_body) > MAX_RESPONSE_BODY:
                    capture_response = False
            await send(message)

        dropped = False
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception:
            dropped = True
            raise
        finally:
            self._record(
                observer,
                scope=scope,
                method=method,
                path=path,
                headers=headers,
                status=status or 499,
                started=started,
                request_body=bytes(request_body),
                response_headers=response_headers,
                response_body=bytes(response_body),
                dropped=dropped,
                template=template,
            )

    def _identity(
        self, observer: Observer, scope: Scope, headers: Mapping[str, str], response: bytes
    ) -> tuple[str, str]:
        client = f"{client_key(scope)}|{headers.get('user-agent', '-')[:64]}"
        identity = resolve_identity(scope)
        if identity.family_id is None:
            identity = self._identity_from_response(scope, response)
        if identity.family_id is not None:
            observer.remember_identity(client, identity.family_id, identity.user or ANONYMOUS)
            return identity.family_id, identity.user or ANONYMOUS
        return observer.sticky_identity(client)

    @staticmethod
    def _identity_from_response(scope: Scope, response: bytes) -> Identity:
        payload = _json_object(response)
        token = payload.get("access_token") if payload else None
        tokens = getattr(getattr(scope.get("app"), "state", None), "tokens", None)
        if isinstance(token, str) and isinstance(tokens, TokenStore):
            try:
                grant = tokens.authenticate(token)
            except Exception:
                return resolve_identity(scope)
            return Identity(grant.family_id, grant.user.email)
        return resolve_identity(scope)

    def _record(
        self,
        observer: Observer,
        *,
        scope: Scope,
        method: str,
        path: str,
        headers: Mapping[str, str],
        status: int,
        started: float,
        request_body: bytes,
        response_headers: Mapping[str, str],
        response_body: bytes,
        dropped: bool,
        template: str,
    ) -> None:
        query = cast(bytes, scope.get("query_string", b"")).decode("latin-1")[:MAX_QUERY_CHARS]
        family_id, user = self._identity(observer, scope, headers, response_body)
        request_payload = _json_object(request_body) if method == "PATCH" else None
        response_payload = _json_object(response_body)
        now_wall = observer.time_source.time()
        record = observer.next_record(
            family_id=family_id,
            user=user,
            method=method,
            route=template or route_template(scope, path),
            path=path,
            query=query,
            query_hash=_query_hash(query),
            status=status,
            duration_ms=round((observer.time_source.monotonic() - started) * 1000, 3),
            has_authorization="authorization" in headers,
            origin=headers.get("origin"),
            idempotency_key=headers.get("idempotency-key"),
            if_match=headers.get("if-match"),
            last_event_id=headers.get("last-event-id"),
            replayed=response_headers.get("idempotent-replayed", "").lower() == "true",
            error_code=(
                cast(str | None, response_payload.get("code"))
                if response_payload and isinstance(response_payload.get("code"), str)
                else None
            ),
            resource_id=(
                cast(str | None, response_payload.get("id"))
                if response_payload and isinstance(response_payload.get("id"), str)
                else None
            ),
            body_keys=tuple(request_payload) if request_payload else (),
            body_fields=_field_hashes(request_payload) if request_payload else {},
            resource_fields=_field_hashes(response_payload) if response_payload else {},
            body_hash=(
                _short_hash(_json_object(request_body))
                if method == "POST" and request_body
                else None
            ),
            retry_after_s=_retry_after_seconds(response_headers.get("retry-after"), now_wall),
            limit_param=_limit_param(query),
            dropped=dropped,
        )
        observer.record(record)


middleware = ObserverMiddleware
"""Picked up by ``main.MIDDLEWARE_PROVIDERS`` (listed last, so it wraps chaos)."""


def get_observer(conn: HTTPConnection) -> Observer:
    return cast(Observer, conn.app.state.observer)


ObserverDep = Annotated[Observer, Depends(get_observer)]


def is_download(record: RequestRecord) -> bool:
    return record.path.endswith(DOWNLOAD_SUFFIXES) or "/files/" in record.path


def records_of(family: FamilyLog, *, since: float | None = None) -> Iterable[RequestRecord]:
    if since is None:
        return list(family.requests)
    return [r for r in family.requests if r.t_mono >= since]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    settings = app.state.settings
    app.state.observer = Observer(
        app.state.time, seed=settings.seed, full_history=settings.full_history
    )
    try:
        yield
    finally:
        app.state.observer.reset()
