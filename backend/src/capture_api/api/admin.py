import secrets
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request, Response, status

from capture_api.deps import SettingsDep
from capture_api.domain.models import (
    AdminExpireTokens,
    AdminRevoke,
    AdminState,
    ChaosConfig,
    HuntTouchResponse,
)
from capture_api.errors import DomainError
from capture_api.platform.chaos import ChaosController
from capture_api.platform.observer import Observer

router = APIRouter(tags=["admin"], include_in_schema=False)

RESETTABLE: tuple[str, ...] = (
    "searches",
    "exports",
    "imports",
    "cases",
    "hunts",
    "bot",
    "bus",
    "idempotency",
    "rate_limiter",
    "login_limiter",
    "tokens",
    "chaos",
    "observer",
)
"""Services reset by ``POST /v1/__admin/reset``: anything here with a ``reset()`` is called."""


def admin_token(request: Request) -> str | None:
    return request.headers.get("x-admin-token") or request.query_params.get("token")


async def require_admin(request: Request, settings: SettingsDep) -> None:
    presented = admin_token(request)
    if presented is None or not secrets.compare_digest(presented, settings.admin_token):
        raise DomainError(
            401,
            "admin_token_invalid",
            "Set X-Admin-Token (or ?token=) to CAP_ADMIN_TOKEN to use the dev endpoints.",
        )


AdminGuard = Depends(require_admin)


def get_chaos(request: Request) -> ChaosController:
    controller = getattr(request.app.state, "chaos", None)
    if not isinstance(controller, ChaosController):
        raise DomainError.unavailable("chaos_unavailable", "Chaos is not configured yet.", 5)
    return controller


def get_observer_state(request: Request) -> Observer | None:
    observer = getattr(request.app.state, "observer", None)
    return observer if isinstance(observer, Observer) else None


ChaosDep = Annotated[ChaosController, Depends(get_chaos)]


@router.get("/__admin/chaos", summary="Current chaos configuration", dependencies=[AdminGuard])
async def get_chaos_config(chaos: ChaosDep) -> ChaosConfig:
    return chaos.config()


@router.put("/__admin/chaos", summary="Set the chaos profile", dependencies=[AdminGuard])
async def set_chaos_config(body: ChaosConfig, chaos: ChaosDep) -> ChaosConfig:
    return chaos.configure(body.profile, body.overrides)


@router.post(
    "/__admin/expire-tokens",
    summary="Expire live access tokens",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[AdminGuard],
)
async def expire_tokens(request: Request, body: AdminExpireTokens | None = None) -> Response:
    request.app.state.tokens.expire_access_tokens(body.email if body else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/__admin/revoke",
    summary="Revoke a user's sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[AdminGuard],
)
async def revoke_user(request: Request, body: AdminRevoke) -> Response:
    request.app.state.tokens.revoke_user(body.email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/__admin/hunts/{hunt_id}/touch",
    summary="Bump a hunt's version (simulate a second tab)",
    dependencies=[AdminGuard],
)
async def touch_hunt(hunt_id: str, request: Request) -> HuntTouchResponse:
    hunts = getattr(request.app.state, "hunts", None)
    touch = getattr(hunts, "touch", None)
    version = touch(hunt_id) if callable(touch) else None
    if version is None:
        raise DomainError.not_found("hunt_not_found", f"No hunt '{hunt_id}'.")
    return HuntTouchResponse(version=int(version))


@router.post(
    "/__admin/reset",
    summary="Clear searches, hunts, cases, imports, tokens and the observer",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[AdminGuard],
)
async def reset_state(request: Request) -> Response:
    state = request.app.state
    world = getattr(state, "world", None)
    clear_imports = getattr(world, "clear_imports", None)
    if callable(clear_imports):
        clear_imports()
    for name in RESETTABLE:
        reset = getattr(getattr(state, name, None), "reset", None)
        if callable(reset):
            reset()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _count(service: Any) -> int:
    for attribute in ("active_count", "count", "__len__"):
        counter = getattr(service, attribute, None)
        if callable(counter):
            try:
                return int(counter())
            except TypeError:  # pragma: no cover - a count() that needs arguments
                continue
    return 0


@router.get("/__admin/state", summary="Counters for debugging", dependencies=[AdminGuard])
async def get_state(request: Request) -> AdminState:
    state = request.app.state
    observer = get_observer_state(request)
    streams, sockets = observer.open_stream_counts() if observer else (0, 0)
    return AdminState(
        families=cast(int, state.tokens.family_count()),
        searches=_count(getattr(state, "searches", None)),
        streams=streams,
        sockets=sockets,
    )
