import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, MutableMapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from fastapi import FastAPI
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from capture_api.domain.models import ChaosConfig, ChaosOverrides, ComponentStatus
from capture_api.errors import DomainError
from capture_api.platform.tokens import TokenStore
from capture_api.settings import ChaosProfile, Settings
from capture_api.world.clock import FakeTimeSource, TimeSource
from capture_api.world.rng import Stream

log = logging.getLogger(__name__)

type FaultKind = Literal["none", "unavailable", "drop"]

EXEMPT_PATHS: frozenset[str] = frozenset(
    {"/v1/health", "/__observer", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}
)
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/v1/auth/",
    "/v1/__admin",
    "/v1/__observer",
    "/__observer",
    "/v1/stream/",
    "/v1/live",
)
SLOW_PATHS: frozenset[str] = frozenset({"/v1/estimate", "/v1/lql/parse"})
"""Routes whose own work is slow: latency is drawn from :data:`SLOW_LATENCY_MS` instead."""

SLOW_LATENCY_MS: tuple[int, int] = (150, 600)
MAX_TRACKED_KEYS = 4096
EXPIRING_ACCESS_TTL_S = 15
DROP_PADDING = 4096


@dataclass(frozen=True, slots=True)
class ProfileParams:
    get_503_rate: float
    drop_rate: float
    latency_ms: tuple[int, int]
    sse_rotate_s: int
    search_pre_commit_rate: float
    search_post_commit_rate: float
    search_fail_rate: float
    ws_restart_s: int | None
    degraded: tuple[str, ...]
    access_ttl_s: int | None = None
    live_burst: int = 0


PROFILES: Mapping[ChaosProfile, ProfileParams] = {
    "calm": ProfileParams(
        get_503_rate=0.0,
        drop_rate=0.0,
        latency_ms=(20, 80),
        sse_rotate_s=300,
        search_pre_commit_rate=0.0,
        search_post_commit_rate=0.0,
        search_fail_rate=0.0,
        ws_restart_s=None,
        degraded=(),
    ),
    "flaky": ProfileParams(
        get_503_rate=0.08,
        drop_rate=0.02,
        latency_ms=(20, 80),
        sse_rotate_s=60,
        search_pre_commit_rate=0.10,
        search_post_commit_rate=0.10,
        search_fail_rate=0.0,
        ws_restart_s=None,
        degraded=(),
    ),
    "storm": ProfileParams(
        get_503_rate=0.20,
        drop_rate=0.05,
        latency_ms=(200, 1500),
        sse_rotate_s=20,
        search_pre_commit_rate=0.10,
        search_post_commit_rate=0.10,
        search_fail_rate=0.01,
        ws_restart_s=90,
        degraded=("index",),
    ),
    "degraded-pcap": ProfileParams(
        get_503_rate=0.0,
        drop_rate=0.0,
        latency_ms=(20, 80),
        sse_rotate_s=300,
        search_pre_commit_rate=0.0,
        search_post_commit_rate=0.0,
        search_fail_rate=0.0,
        ws_restart_s=None,
        degraded=("pcap_store",),
    ),
    "expiring-tokens": ProfileParams(
        get_503_rate=0.0,
        drop_rate=0.0,
        latency_ms=(20, 80),
        sse_rotate_s=300,
        search_pre_commit_rate=0.0,
        search_post_commit_rate=0.0,
        search_fail_rate=0.0,
        ws_restart_s=None,
        degraded=(),
        access_ttl_s=EXPIRING_ACCESS_TTL_S,
    ),
}

COMPONENT_DETAIL: Mapping[str, str] = {
    "index": "The session index is rebuilding; searches may be slow or fail.",
    "decoder": "The decoder pool is degraded.",
    "pcap_store": "The packet store is degraded; downloads answer 503.",
    "live_feed": "The live feed is degraded.",
}
COMPONENT_NAMES: tuple[str, ...] = ("index", "decoder", "pcap_store", "live_feed")


class ChaosDroppedConnection(Exception): ...


@dataclass(frozen=True, slots=True)
class Identity:
    family_id: str | None
    user: str | None


@dataclass(frozen=True, slots=True)
class Decision:
    key: str
    counter: int
    latency_s: float
    fault: FaultKind
    retry_after_s: int


@dataclass(frozen=True, slots=True)
class SearchDecision:
    pre_commit_503: bool
    post_commit_503: bool
    fail_during_scan: bool
    retry_after_s: int


def bearer_token(scope: Scope) -> str | None:
    headers = cast(Iterable[tuple[bytes, bytes]], scope.get("headers", ()))
    for name, value in headers:
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                return token.strip()
    return None


def client_key(scope: Scope) -> str:
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return f"ip:{client[0]}"
    return "ip:unknown"


def resolve_identity(scope: Scope) -> Identity:
    state = scope.get("state") or {}
    auth = state.get("auth") if isinstance(state, Mapping) else None
    family_id = getattr(auth, "family_id", None)
    if isinstance(family_id, str):
        user = getattr(getattr(auth, "user", None), "email", None)
        return Identity(family_id, user if isinstance(user, str) else None)
    token = bearer_token(scope)
    app = scope.get("app")
    tokens = getattr(getattr(app, "state", None), "tokens", None)
    if token is not None and isinstance(tokens, TokenStore):
        with suppress(DomainError):
            grant = tokens.authenticate(token)
            return Identity(grant.family_id, grant.user.email)
    return Identity(None, None)


def is_exempt(path: str) -> bool:
    return path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES)


async def _no_sleep(_seconds: float) -> None:
    return None


class ChaosController:
    def __init__(
        self,
        *,
        settings: Settings,
        tokens: TokenStore | None = None,
        time_source: TimeSource | None = None,
        profile: ChaosProfile | None = None,
    ) -> None:
        self._settings = settings
        self._tokens = tokens
        self._seed = settings.seed
        self._profile: ChaosProfile = profile or settings.chaos
        self._overrides = ChaosOverrides()
        self._counters: MutableMapping[str, int] = {}
        self._default_access_ttl: Callable[[], float] | None = (
            tokens.access_ttl if tokens is not None else None
        )
        real_clock = time_source is not None and not isinstance(time_source, FakeTimeSource)
        self._sleep: Callable[[float], Awaitable[None]] = asyncio.sleep if real_clock else _no_sleep
        """With an injected fake clock chaos decides a latency but does not really wait."""
        self._apply_access_ttl()

    @property
    def seed(self) -> str:
        return self._seed

    @property
    def profile(self) -> ChaosProfile:
        return self._profile

    @property
    def params(self) -> ProfileParams:
        base = PROFILES[self._profile]
        o = self._overrides
        return replace(
            base,
            get_503_rate=base.get_503_rate if o.get_503_rate is None else o.get_503_rate,
            drop_rate=base.drop_rate if o.drop_rate is None else o.drop_rate,
            latency_ms=base.latency_ms if o.latency_ms is None else o.latency_ms,
            sse_rotate_s=base.sse_rotate_s if o.sse_rotate_s is None else o.sse_rotate_s,
            access_ttl_s=base.access_ttl_s if o.access_ttl_s is None else o.access_ttl_s,
            live_burst=base.live_burst if o.live_burst is None else o.live_burst,
        )

    @property
    def sse_rotate_s(self) -> int:
        return self.params.sse_rotate_s

    @property
    def ws_restart_s(self) -> int | None:
        return self.params.ws_restart_s

    @property
    def live_burst(self) -> int:
        return self.params.live_burst

    @property
    def access_ttl_s(self) -> int:
        return self.params.access_ttl_s or self._settings.access_ttl_s

    @property
    def pcap_degraded(self) -> bool:
        return "pcap_store" in self.params.degraded

    def components(self) -> dict[str, ComponentStatus]:
        degraded = set(self.params.degraded)
        return {
            name: ComponentStatus(
                status="degraded" if name in degraded else "ok",
                detail=COMPONENT_DETAIL[name] if name in degraded else None,
            )
            for name in COMPONENT_NAMES
        }

    def config(self) -> ChaosConfig:
        p = self.params
        return ChaosConfig(
            profile=self._profile,
            overrides=ChaosOverrides(
                get_503_rate=p.get_503_rate,
                drop_rate=p.drop_rate,
                latency_ms=p.latency_ms,
                sse_rotate_s=p.sse_rotate_s,
                access_ttl_s=self.access_ttl_s,
                live_burst=p.live_burst,
            ),
        )

    def configure(
        self, profile: ChaosProfile, overrides: ChaosOverrides | None = None
    ) -> ChaosConfig:
        self._profile = profile
        self._overrides = overrides or ChaosOverrides()
        self._apply_access_ttl()
        log.info("chaos profile set to %s", profile)
        return self.config()

    def _apply_access_ttl(self) -> None:
        if self._tokens is None:
            return
        ttl = float(self.access_ttl_s)
        self._tokens.access_ttl = lambda: ttl

    def close(self) -> None:
        if self._tokens is not None and self._default_access_ttl is not None:
            self._tokens.access_ttl = self._default_access_ttl

    def reset(self) -> None:
        self._counters.clear()

    def key_for(self, scope: Scope | HTTPConnection) -> str:
        raw = scope.scope if isinstance(scope, HTTPConnection) else scope
        identity = resolve_identity(raw)
        return identity.family_id or client_key(raw)

    def counter(self, key: str) -> int:
        return self._counters.get(key, 0)

    def _bump(self, key: str) -> int:
        if len(self._counters) > MAX_TRACKED_KEYS and key not in self._counters:
            self._counters.clear()
        counter = self._counters.get(key, 0) + 1
        self._counters[key] = counter
        return counter

    def latency_ms(self, *, slow: bool = False) -> tuple[int, int]:
        low, high = self.params.latency_ms
        if slow:
            return max(low, SLOW_LATENCY_MS[0]), max(high, SLOW_LATENCY_MS[1])
        return low, high

    def decide(self, key: str, *, method: str = "GET", slow: bool = False) -> Decision:
        counter = self._bump(key)
        return self.decision_at(key, counter, method=method, slow=slow)

    def decision_at(
        self, key: str, counter: int, *, method: str = "GET", slow: bool = False
    ) -> Decision:
        params = self.params
        stream = Stream(self._seed, "chaos", key, counter)
        low, high = self.latency_ms(slow=slow)
        latency_s = stream.randint(low, high) / 1000.0
        fault: FaultKind = "none"
        retry_after_s = 1
        if method.upper() == "GET":
            roll = stream.random()
            if roll < params.get_503_rate:
                fault = "unavailable"
                retry_after_s = stream.randint(1, 3)
            elif roll < params.get_503_rate + params.drop_rate:
                fault = "drop"
        return Decision(
            key=key,
            counter=counter,
            latency_s=latency_s,
            fault=fault,
            retry_after_s=retry_after_s,
        )

    def search_decision(self, key: str | Scope | HTTPConnection) -> SearchDecision:
        chaos_key = key if isinstance(key, str) else self.key_for(key)
        params = self.params
        stream = Stream(self._seed, "chaos", chaos_key, self.counter(chaos_key), "search")
        return SearchDecision(
            pre_commit_503=stream.chance(params.search_pre_commit_rate),
            post_commit_503=stream.chance(params.search_post_commit_rate),
            fail_during_scan=stream.chance(params.search_fail_rate),
            retry_after_s=stream.randint(1, 3),
        )

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await self._sleep(seconds)

    def unavailable_error(self, retry_after_s: int) -> DomainError:
        return DomainError.unavailable(
            "unavailable",
            "The sensor grid is temporarily unavailable; retry after the suggested delay.",
            retry_after_s,
        )


def _unavailable_response(retry_after_s: int) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    body = json.dumps(
        {
            "detail": (
                "The sensor grid is temporarily unavailable; retry after the suggested delay."
            ),
            "code": "unavailable",
        }
    ).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"retry-after", str(retry_after_s).encode()),
    ]
    return body, headers


class ChaosMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = getattr(scope.get("app"), "state", None)
        controller = cast(ChaosController | None, getattr(state, "chaos", None))
        path = cast(str, scope["path"])
        if controller is None or is_exempt(path):
            await self.app(scope, receive, send)
            return

        decision = controller.decide(
            controller.key_for(scope),
            method=cast(str, scope.get("method", "GET")),
            slow=path in SLOW_PATHS,
        )
        scope_state = scope.get("state")
        if isinstance(scope_state, dict):
            scope_state["chaos_decision"] = decision
        await controller.sleep(decision.latency_s)

        if decision.fault == "unavailable":
            body, headers = _unavailable_response(decision.retry_after_s)
            await send({"type": "http.response.start", "status": 503, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return
        if decision.fault == "drop":
            await self._drop(send, decision)
            return
        await self.app(scope, receive, send)

    async def _drop(self, send: Send, decision: Decision) -> None:
        body = b'{"items":[{"id":"'
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body) + DROP_PADDING).encode()),
        ]
        start: Message = {"type": "http.response.start", "status": 200, "headers": headers}
        await send(start)
        await send({"type": "http.response.body", "body": body, "more_body": True})
        raise ChaosDroppedConnection(
            f"chaos dropped the connection for {decision.key} (#{decision.counter})"
        )


middleware = ChaosMiddleware
"""Picked up by ``main.MIDDLEWARE_PROVIDERS``."""


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    controller = ChaosController(
        settings=app.state.settings,
        tokens=app.state.tokens,
        time_source=app.state.time,
    )
    app.state.chaos = controller
    try:
        yield
    finally:
        controller.close()
