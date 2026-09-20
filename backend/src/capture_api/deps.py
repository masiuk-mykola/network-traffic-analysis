from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import HTTPConnection

from capture_api.domain.models import Permission, Profile, Role
from capture_api.errors import DomainError
from capture_api.platform.login_limit import LoginLimiter
from capture_api.platform.permissions import (
    User,
    build_profile,
    can_read_sensor,
    has_permission,
)
from capture_api.platform.ratelimit import RateLimiter
from capture_api.platform.tokens import TokenStore
from capture_api.settings import Settings
from capture_api.world.catalog import BUILTIN_SENSOR_IDS
from capture_api.world.clock import CaptureClock, TimeSource
from capture_api.world.types import World

bearer_scheme = HTTPBearer(
    scheme_name="bearer",
    description="Access token `at_…` from POST /v1/auth/login or /v1/auth/refresh.",
    auto_error=False,
)


def get_settings_dep(conn: HTTPConnection) -> Settings:
    return cast(Settings, conn.app.state.settings)


def get_time(conn: HTTPConnection) -> TimeSource:
    return cast(TimeSource, conn.app.state.time)


def get_clock(conn: HTTPConnection) -> CaptureClock:
    return cast(CaptureClock, conn.app.state.clock)


def get_tokens(conn: HTTPConnection) -> TokenStore:
    return cast(TokenStore, conn.app.state.tokens)


def get_login_limiter(conn: HTTPConnection) -> LoginLimiter:
    return cast(LoginLimiter, conn.app.state.login_limiter)


def get_rate_limiter(conn: HTTPConnection) -> RateLimiter:
    limiter = getattr(conn.app.state, "rate_limiter", None)
    if limiter is None:
        raise DomainError.unavailable("rate_limiter_unavailable", "Rate limits are not ready.", 5)
    return cast(RateLimiter, limiter)


def get_world(conn: HTTPConnection) -> World:
    world = getattr(conn.app.state, "world", None)
    if world is None:
        raise DomainError.unavailable("world_unavailable", "The world is not loaded yet.", 5)
    return cast(World, world)


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
TimeDep = Annotated[TimeSource, Depends(get_time)]
ClockDep = Annotated[CaptureClock, Depends(get_clock)]
TokensDep = Annotated[TokenStore, Depends(get_tokens)]
LoginLimiterDep = Annotated[LoginLimiter, Depends(get_login_limiter)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
WorldDep = Annotated[World, Depends(get_world)]


def known_sensor_ids(conn: HTTPConnection) -> list[str]:
    world = getattr(conn.app.state, "world", None)
    if world is None:
        return list(BUILTIN_SENSOR_IDS)
    return [s.id for s in cast(World, world).sensors()]


@dataclass(frozen=True, slots=True)
class AuthContext:
    family_id: str
    user: User
    profile: Profile
    token: str
    expires_at: float
    """Monotonic seconds at which the access token expires (as of authentication)."""

    @property
    def role(self) -> Role:
        return self.user.role

    @property
    def user_id(self) -> str:
        return self.user.id

    def can(self, permission: Permission) -> bool:
        return has_permission(self.user.role, permission)

    def can_read_sensor(self, sensor_id: str) -> bool:
        return can_read_sensor(self.user.role, sensor_id)


def bearer_token(conn: HTTPConnection) -> str | None:
    header = conn.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


async def current_auth(
    conn: HTTPConnection,
    tokens: TokensDep,
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    grant = tokens.authenticate(bearer_token(conn))
    profile = build_profile(grant.user, known_sensor_ids(conn))
    auth = AuthContext(
        family_id=grant.family_id,
        user=grant.user,
        profile=profile,
        token=grant.token,
        expires_at=grant.expires_at,
    )
    conn.scope.setdefault("state", {})["auth"] = auth
    return auth


CurrentAuth = Annotated[AuthContext, Depends(current_auth)]
"""The authenticated caller (any role)."""

CurrentFamily = CurrentAuth
"""Alias naming the token family the caller belongs to."""


def require_permission(
    permission: Permission,
) -> Callable[[AuthContext], Coroutine[Any, Any, AuthContext]]:

    async def dependency(auth: CurrentAuth) -> AuthContext:
        if not auth.can(permission):
            raise DomainError.forbidden(permission)
        return auth

    dependency.__name__ = f"require_{permission.replace(':', '_')}"
    return dependency


def check_sensors(auth: AuthContext, sensor_ids: Iterable[str]) -> None:
    for sensor_id in sensor_ids:
        if not auth.can_read_sensor(sensor_id):
            raise DomainError.forbidden_sensor(sensor_id)
