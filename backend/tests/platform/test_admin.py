from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import ADMIN_HEADERS, ClientFactory

ANALYST = {"email": "ana@quillmere.example", "password": "demo-analyst"}
ADMIN_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/v1/__admin/chaos"),
    ("PUT", "/v1/__admin/chaos"),
    ("POST", "/v1/__admin/expire-tokens"),
    ("POST", "/v1/__admin/revoke"),
    ("POST", "/v1/__admin/hunts/hnt_1/touch"),
    ("POST", "/v1/__admin/reset"),
    ("GET", "/v1/__admin/state"),
)


def login(client: TestClient) -> dict[str, Any]:
    response = client.post("/v1/auth/login", json=ANALYST)
    assert response.status_code == 200
    return dict(response.json())


def auth_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {login(client)['access_token']}"}


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_every_admin_route_requires_the_token(
    make_client: ClientFactory, method: str, path: str
) -> None:
    client = make_client()
    response = client.request(method, path, json={})
    assert response.status_code == 401
    assert response.json()["code"] == "admin_token_invalid"
    assert (
        client.request(method, path, json={}, headers={"X-Admin-Token": "wrong"}).status_code == 401
    )


def test_admin_routes_stay_out_of_the_schema(make_client: ClientFactory) -> None:
    paths = make_client().get("/openapi.json").json()["paths"]
    assert not [path for path in paths if "__admin" in path or "__observer" in path]


def test_get_and_put_chaos(make_client: ClientFactory) -> None:
    client = make_client()
    current = client.get("/v1/__admin/chaos", headers=ADMIN_HEADERS).json()
    assert current["profile"] == "calm"
    assert current["overrides"]["get_503_rate"] == 0.0
    updated = client.put(
        "/v1/__admin/chaos",
        headers=ADMIN_HEADERS,
        json={"profile": "flaky", "overrides": {"sse_rotate_s": 5, "live_burst": 3}},
    ).json()
    assert updated["profile"] == "flaky"
    assert updated["overrides"]["sse_rotate_s"] == 5
    assert updated["overrides"]["live_burst"] == 3
    assert updated["overrides"]["get_503_rate"] == 0.08
    assert client.get("/v1/__admin/chaos", headers=ADMIN_HEADERS).json() == updated


def test_put_chaos_rejects_an_unknown_profile(make_client: ClientFactory) -> None:
    response = make_client().put(
        "/v1/__admin/chaos", headers=ADMIN_HEADERS, json={"profile": "hurricane"}
    )
    assert response.status_code == 422


def test_expire_tokens_makes_the_next_call_token_expired(make_client: ClientFactory) -> None:
    client = make_client()
    headers = auth_headers(client)
    assert client.get("/v1/me", headers=headers).status_code == 200
    assert client.post("/v1/__admin/expire-tokens", headers=ADMIN_HEADERS).status_code == 204
    response = client.get("/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "token_expired"


def test_expire_tokens_can_target_one_user(make_client: ClientFactory) -> None:
    client = make_client()
    headers = auth_headers(client)
    response = client.post(
        "/v1/__admin/expire-tokens",
        headers=ADMIN_HEADERS,
        json={"email": "oli@quillmere.example"},
    )
    assert response.status_code == 204
    assert client.get("/v1/me", headers=headers).status_code == 200


def test_revoke_kills_the_session(make_client: ClientFactory) -> None:
    client = make_client()
    headers = auth_headers(client)
    response = client.post(
        "/v1/__admin/revoke", headers=ADMIN_HEADERS, json={"email": ANALYST["email"]}
    )
    assert response.status_code == 204
    assert client.get("/v1/me", headers=headers).json()["code"] == "session_revoked"


def test_touch_hunt_is_404_without_a_hunts_service(make_client: ClientFactory) -> None:
    client = make_client()
    response = client.post("/v1/__admin/hunts/hnt_1/touch", headers=ADMIN_HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "hunt_not_found"


def test_touch_hunt_calls_the_hunts_service(make_client: ClientFactory) -> None:
    client = make_client()

    class Hunts:
        def __init__(self) -> None:
            self.versions = {"hnt_1": 1}

        def touch(self, hunt_id: str) -> int | None:
            if hunt_id not in self.versions:
                return None
            self.versions[hunt_id] += 1
            return self.versions[hunt_id]

    client.app.state.hunts = Hunts()  # type: ignore[attr-defined]
    response = client.post("/v1/__admin/hunts/hnt_1/touch", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"version": 2}
    assert client.post("/v1/__admin/hunts/nope/touch", headers=ADMIN_HEADERS).status_code == 404


def test_reset_clears_tokens_the_observer_and_registered_services(
    make_client: ClientFactory,
) -> None:
    client = make_client()
    headers = auth_headers(client)
    client.get("/v1/me", headers=headers)
    observer = client.app.state.observer  # type: ignore[attr-defined]
    assert observer.request_count() > 0
    reset_calls: list[str] = []

    class Service:
        def reset(self) -> None:
            reset_calls.append("searches")

    client.app.state.searches = Service()  # type: ignore[attr-defined]
    assert client.post("/v1/__admin/reset", headers=ADMIN_HEADERS).status_code == 204
    assert reset_calls == ["searches"]
    assert client.get("/v1/me", headers=headers).json()["code"] == "invalid_token"
    assert client.app.state.tokens.family_count() == 0  # type: ignore[attr-defined]


def test_state_reports_counters(make_client: ClientFactory) -> None:
    client = make_client()
    auth_headers(client)
    observer = client.app.state.observer  # type: ignore[attr-defined]
    observer.sse_opened("fam_x", "ana@quillmere.example")
    observer.ws_opened("fam_x", "ana@quillmere.example")
    body = client.get("/v1/__admin/state", headers=ADMIN_HEADERS).json()
    assert body == {"families": 1, "searches": 0, "streams": 1, "sockets": 1}
