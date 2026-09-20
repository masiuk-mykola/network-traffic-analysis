from fastapi import APIRouter, Depends, Request, Response, status

from capture_api.deps import (
    CurrentAuth,
    LoginLimiterDep,
    TokensDep,
    bearer_scheme,
    bearer_token,
    known_sensor_ids,
)
from capture_api.domain.models import LoginRequest, Profile, RefreshRequest, TokenPair
from capture_api.errors import DomainError, error_responses
from capture_api.platform.permissions import build_profile, user_by_email
from capture_api.platform.tokens import IssuedTokens

router = APIRouter(tags=["auth"])


def _token_pair(request: Request, issued: IssuedTokens) -> TokenPair:
    return TokenPair(
        access_token=issued.access_token,
        token_type="bearer",  # noqa: S106 - the OAuth token type, not a secret
        access_expires_in=issued.access_expires_in,
        refresh_token=issued.refresh_token,
        refresh_expires_in=issued.refresh_expires_in,
        user=build_profile(issued.user, known_sensor_ids(request)),
    )


@router.post(
    "/auth/login",
    summary="Sign in with email and password",
    description=(
        "Creates a token family. After 5 failed attempts for one email within 60 s the "
        "endpoint answers 429 `login_rate_limited` whose `Retry-After` is an HTTP-date "
        "(not seconds)."
    ),
    response_model=TokenPair,
    responses=error_responses(401, 429, bearer=False),
)
async def login(
    body: LoginRequest,
    request: Request,
    tokens: TokensDep,
    limiter: LoginLimiterDep,
) -> TokenPair:
    limiter.check(body.email)
    user = user_by_email(body.email)
    if user is None or user.password != body.password:
        limiter.record_failure(body.email)
        raise DomainError(401, "invalid_credentials", "Unknown email or wrong password.")
    limiter.record_success(body.email)
    return _token_pair(request, tokens.login(user))


@router.post(
    "/auth/refresh",
    summary="Rotate the refresh token",
    description=(
        "Consumes the refresh token (single use, zero grace) and returns a new pair. "
        "Re-presenting a consumed token revokes the whole session (`refresh_reused`)."
    ),
    response_model=TokenPair,
    responses=error_responses(401, bearer=False),
)
async def refresh(body: RefreshRequest, request: Request, tokens: TokensDep) -> TokenPair:
    return _token_pair(request, tokens.refresh(body.refresh_token))


@router.post(
    "/auth/logout",
    summary="Revoke the current session",
    description="Revokes the token family. Idempotent; an expired access token is accepted.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401),
    dependencies=[Depends(bearer_scheme)],
)
async def logout(request: Request, tokens: TokensDep) -> Response:
    token = bearer_token(request)
    if token is None:
        raise DomainError.unauthorized("invalid_token", "Missing Bearer token.")
    tokens.logout(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    summary="The signed-in user's profile",
    response_model=Profile,
    responses=error_responses(401),
)
async def get_me(auth: CurrentAuth) -> Profile:
    return auth.profile
