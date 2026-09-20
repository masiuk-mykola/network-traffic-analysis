import importlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from types import ModuleType
from typing import Any, cast

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from capture_api import __version__
from capture_api.api import (
    admin,
    analytics,
    auth,
    cases,
    detections,
    enrich,
    health,
    hunts,
    imports,
    live,
    meta,
    observer,
    searches,
    sensors,
    sessions,
)
from capture_api.errors import install_error_handlers
from capture_api.platform.login_limit import LoginLimiter
from capture_api.platform.tokens import TokenStore
from capture_api.settings import Settings, get_settings
from capture_api.world.clock import CaptureClock, SystemTimeSource, TimeSource

log = logging.getLogger(__name__)

API_PREFIX = "/v1"

ROUTER_MODULES: tuple[ModuleType, ...] = (
    auth,
    health,
    sensors,
    meta,
    searches,
    analytics,
    sessions,
    enrich,
    detections,
    live,
    hunts,
    cases,
    imports,
    admin,
    observer,
)
"""Every API module; each exposes ``router`` (and optionally ``root_router``)."""

SERVICE_PROVIDERS: tuple[str, ...] = (
    "capture_api.world.world",
    "capture_api.platform.ratelimit",
    "capture_api.platform.idempotency",
    "capture_api.platform.chaos",
    "capture_api.platform.observer",
    "capture_api.realtime.bus",
    "capture_api.search.jobs",
    "capture_api.workspace.hunts",
    "capture_api.workspace.cases",
    "capture_api.workspace.exports",
    "capture_api.workspace.imports",
    "capture_api.workspace.bot",
)
"""Modules exposing ``lifespan(app: FastAPI) -> AbstractAsyncContextManager[None]``,
entered in this order at start-up and exited in reverse at shutdown."""

MIDDLEWARE_PROVIDERS: tuple[str, ...] = (
    "capture_api.platform.chaos",
    "capture_api.platform.observer",
)
"""Modules exposing ``middleware``: a pure ASGI middleware class ``cls(app)``. Listed
innermost first, so the observer wraps chaos and records every faulted response."""

OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "auth", "description": "Sign-in, rotating refresh tokens, logout, profile."},
    {"name": "platform", "description": "Health and sensors."},
    {"name": "meta", "description": "Filter fields, grid columns, enums, protocol schemas."},
    {"name": "search", "description": "Match estimates and the long-running search job."},
    {"name": "sessions", "description": "Session detail, flow, carved files, PCAP."},
    {"name": "enrichment", "description": "IP enrichment."},
    {"name": "detections", "description": "Detection backfill and the SSE live feed."},
    {"name": "hunts", "description": "Private saved hunts (ETag / If-Match)."},
    {"name": "live", "description": "WebSocket live-tap tickets."},
    {"name": "imports", "description": "Capture import (multipart upload + indexing job)."},
    {"name": "cases", "description": "Shared cases, evidence, notes and exports."},
    {"name": "analytics", "description": "LQL parsing, histogram, pivots, conversation graph."},
]

DESCRIPTION = (
    "Deterministic traffic-forensics simulator. "
    "Browsers cannot call it directly (no CORS): proxy it from your own server. Optional "
    "fields are absent rather than null; times are ISO-8601 UTC with milliseconds; session "
    "ids are uint64 decimal strings."
)


def operation_id(route: APIRoute) -> str:
    head, *rest = route.name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _optional_module(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise


type LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _providers() -> list[tuple[str, LifespanFactory]]:
    found: list[tuple[str, LifespanFactory]] = []
    for name in SERVICE_PROVIDERS:
        module = _optional_module(name)
        if module is None:
            log.debug("service provider %s not present; skipped", name)
            continue
        factory = getattr(module, "lifespan", None)
        if factory is None:
            raise RuntimeError(f"{name} is listed as a service provider but has no lifespan()")
        found.append((name, cast(LifespanFactory, factory)))
    return found


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        for name, factory in _providers():
            log.debug("starting %s", name)
            await stack.enter_async_context(factory(app))
        yield


def _install_middleware(app: FastAPI) -> None:
    for name in MIDDLEWARE_PROVIDERS:
        module = _optional_module(name)
        if module is None:
            continue
        middleware = getattr(module, "middleware", None)
        if middleware is None:
            raise RuntimeError(f"{name} is listed as a middleware provider but has no middleware")
        app.add_middleware(middleware)


def _mount(app: FastAPI, module: ModuleType) -> None:
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise TypeError(f"{module.__name__} must define `router: APIRouter`")
    app.include_router(router, prefix=API_PREFIX)
    root_router = getattr(module, "root_router", None)
    if isinstance(root_router, APIRouter):
        app.include_router(root_router)


def create_app(
    settings: Settings | None = None, *, time_source: TimeSource | None = None
) -> FastAPI:
    settings = settings or get_settings()
    time_source = time_source or SystemTimeSource()

    app = FastAPI(
        title="Capture API Simulator API",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=_lifespan,
        generate_unique_id_function=operation_id,
        separate_input_output_schemas=False,
    )

    app.state.settings = settings
    app.state.time = time_source
    app.state.clock = CaptureClock(settings.epoch, time_source)
    app.state.tokens = TokenStore(
        seed=settings.seed,
        time_source=time_source,
        access_ttl=lambda: float(settings.access_ttl_s),
        refresh_idle_s=settings.refresh_idle_s,
        refresh_max_s=settings.refresh_max_s,
    )
    app.state.login_limiter = LoginLimiter(time_source)

    install_error_handlers(app)
    for module in ROUTER_MODULES:
        _mount(app, module)
    _install_middleware(app)
    return app
