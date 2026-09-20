from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from fastapi.testclient import TestClient

from capture_api.world.clock import FakeTimeSource
from tests.conftest import ANALYST, OBSERVER, LoggedIn

LOGIN = "/v1/auth/login"


def test_login_returns_a_token_pair_with_the_profile(login: Callable[..., LoggedIn]) -> None:
    body = login().body
    assert body["token_type"] == "bearer"
    assert body["access_expires_in"] == 90
    assert body["refresh_expires_in"] == 1800
    assert body["user"] == {
        "id": "ana",
        "email": "ana@quillmere.example",
        "display_name": "Ana Duarte",
        "role": "analyst",
        "permissions": [
            "sessions:read",
            "pcap:download",
            "files:download",
            "hunts:write",
            "cases:write",
            "imports:create",
            "live:read",
        ],
        "sensor_ids": ["hq-core", "dc-east", "harbor-branch"],
    }


def test_observer_profile_excludes_dc_east(login: Callable[..., LoggedIn]) -> None:
    user = login(*OBSERVER).body["user"]
    assert isinstance(user, dict)
    assert user["role"] == "observer"
    assert user["permissions"] == ["sessions:read", "live:read"]
    assert user["sensor_ids"] == ["hq-core", "harbor-branch"]


def test_wrong_credentials(client: TestClient) -> None:
    r = client.post(LOGIN, json={"email": ANALYST[0], "password": "nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_credentials"
    r = client.post(LOGIN, json={"email": "who@quillmere.example", "password": "demo-analyst"})
    assert r.json()["code"] == "invalid_credentials"


def test_login_body_validation_is_a_default_422(client: TestClient) -> None:
    r = client.post(LOGIN, json={"email": ANALYST[0]})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "password"]
    r = client.post(LOGIN, json={**dict(zip(("email", "password"), ANALYST, strict=True)), "x": 1})
    assert r.status_code == 422


def test_login_rate_limit_uses_an_http_date(client: TestClient, fake_time: FakeTimeSource) -> None:
    for _ in range(5):
        assert client.post(LOGIN, json={"email": ANALYST[0], "password": "x"}).status_code == 401
    fake_time.advance(10)
    r = client.post(LOGIN, json={"email": "ANA@quillmere.example", "password": ANALYST[1]})
    assert r.status_code == 429
    assert r.json()["code"] == "login_rate_limited"
    retry_at = parsedate_to_datetime(r.headers["retry-after"])
    now = datetime.fromtimestamp(fake_time.time(), tz=UTC)
    assert 45 <= (retry_at - now).total_seconds() <= 51
    other = client.post(LOGIN, json={"email": OBSERVER[0], "password": OBSERVER[1]})
    assert other.status_code == 200
    fake_time.advance(50)
    assert client.post(LOGIN, json={"email": ANALYST[0], "password": ANALYST[1]}).status_code == 200


def test_me(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    session = login()
    r = client.get("/v1/me", headers=session.headers)
    assert r.status_code == 200
    assert r.json()["email"] == ANALYST[0]


def test_me_without_or_with_bad_token(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer at_bogus"}, {"Authorization": "Basic x"}):
        r = client.get("/v1/me", headers=headers)
        assert r.status_code == 401
        assert r.json()["code"] == "invalid_token"
        assert r.headers["www-authenticate"] == 'Bearer error="invalid_token"'


def test_expired_access_token(
    client: TestClient, login: Callable[..., LoggedIn], fake_time: FakeTimeSource
) -> None:
    session = login()
    fake_time.advance(91)
    r = client.get("/v1/me", headers=session.headers)
    assert (r.status_code, r.json()["code"]) == (401, "token_expired")


def test_refresh_rotation_and_reuse(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    session = login()
    r = client.post("/v1/auth/refresh", json={"refresh_token": session.refresh_token})
    assert r.status_code == 200
    rotated = r.json()
    assert rotated["refresh_token"] != session.refresh_token
    assert client.get("/v1/me", headers=session.headers).status_code == 200

    reused = client.post("/v1/auth/refresh", json={"refresh_token": session.refresh_token})
    assert (reused.status_code, reused.json()["code"]) == (401, "refresh_reused")
    r = client.get("/v1/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert (r.status_code, r.json()["code"]) == (401, "session_revoked")


def test_refresh_unknown_token(client: TestClient) -> None:
    r = client.post("/v1/auth/refresh", json={"refresh_token": "rt_nope"})
    assert (r.status_code, r.json()["code"]) == (401, "refresh_invalid")


def test_logout(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    session = login()
    first = client.post("/v1/auth/logout", headers=session.headers)
    assert first.status_code == 204
    assert first.content == b""
    assert client.post("/v1/auth/logout", headers=session.headers).status_code == 204
    r = client.get("/v1/me", headers=session.headers)
    assert (r.status_code, r.json()["code"]) == (401, "session_revoked")
    refresh = client.post("/v1/auth/refresh", json={"refresh_token": session.refresh_token})
    assert refresh.status_code == 401
    assert client.post("/v1/auth/logout").status_code == 401


def test_admin_hooks_through_app_state(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    session = login()
    tokens = client.app.state.tokens  # type: ignore[attr-defined]
    tokens.expire_access_tokens(ANALYST[0])
    assert client.get("/v1/me", headers=session.headers).json()["code"] == "token_expired"
    tokens.revoke_user(ANALYST[0])
    assert client.get("/v1/me", headers=session.headers).json()["code"] == "session_revoked"
