from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

from capture_api.domain.models import ChaosOverrides
from capture_api.platform.chaos import (
    ChaosController,
    ChaosDroppedConnection,
    ChaosMiddleware,
    Decision,
    is_exempt,
)
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource

from .conftest import ADMIN_HEADERS, ClientFactory


def controller(profile: str = "calm", seed: str = "test") -> ChaosController:
    settings = Settings(_env_file=None, seed=seed, chaos=profile)  # type: ignore[arg-type]
    return ChaosController(settings=settings, time_source=FakeTimeSource())


def decisions(chaos: ChaosController, key: str, count: int) -> list[Decision]:
    return [chaos.decide(key) for _ in range(count)]


def test_same_seed_family_and_counter_replay_the_same_decisions() -> None:
    first, second = controller("storm"), controller("storm")
    assert decisions(first, "fam_a", 40) == decisions(second, "fam_a", 40)


def test_a_different_family_gets_a_different_fault_sequence() -> None:
    chaos = controller("storm")
    a = [d.fault for d in decisions(chaos, "fam_a", 60)]
    b = [d.fault for d in decisions(chaos, "fam_b", 60)]
    assert a != b


def test_decision_at_is_pure() -> None:
    chaos = controller("flaky")
    chaos.decide("fam_a")
    chaos.decide("fam_a")
    assert chaos.counter("fam_a") == 2
    assert chaos.decision_at("fam_a", 2) == chaos.decision_at("fam_a", 2)
    assert chaos.counter("fam_a") == 2


def test_calm_never_faults_and_storm_does_both() -> None:
    calm = [d.fault for d in decisions(controller("calm"), "fam_a", 200)]
    assert set(calm) == {"none"}
    storm = [d.fault for d in decisions(controller("storm"), "fam_a", 400)]
    assert "unavailable" in storm
    assert "drop" in storm


def test_non_get_methods_are_never_faulted() -> None:
    chaos = controller("storm")
    faults = {chaos.decide("fam_a", method="POST").fault for _ in range(200)}
    assert faults == {"none"}


def test_storm_latency_is_higher_than_calm_and_slow_routes_are_slower() -> None:
    calm, storm = controller("calm"), controller("storm")
    assert calm.latency_ms() == (20, 80)
    assert storm.latency_ms() == (200, 1500)
    assert calm.latency_ms(slow=True) == (150, 600)
    assert max(d.latency_s for d in decisions(storm, "fam_a", 20)) > 0.1


def test_overrides_replace_profile_values() -> None:
    chaos = controller("calm")
    config = chaos.configure("calm", chaos.config().overrides)
    assert config.profile == "calm"
    chaos.configure("calm", ChaosOverrides(get_503_rate=1.0, latency_ms=(0, 0), live_burst=7))
    decision = chaos.decide("fam_a")
    assert decision.fault == "unavailable"
    assert decision.latency_s == 0.0
    assert chaos.live_burst == 7


def test_expiring_tokens_profile_sets_the_access_ttl() -> None:
    settings = Settings(_env_file=None, seed="test", access_ttl_s=90)

    class FakeTokens:
        def __init__(self) -> None:
            self.access_ttl: Any = lambda: 90.0

    tokens = FakeTokens()
    chaos = ChaosController(
        settings=settings,
        tokens=tokens,  # type: ignore[arg-type]
        time_source=FakeTimeSource(),
    )
    assert chaos.access_ttl_s == 90
    assert tokens.access_ttl() == 90.0
    chaos.configure("expiring-tokens")
    assert chaos.access_ttl_s == 15
    assert tokens.access_ttl() == 15.0
    chaos.close()
    assert tokens.access_ttl() == 90.0


def test_degraded_components_follow_the_profile() -> None:
    assert controller("calm").components()["pcap_store"].status == "ok"
    assert controller("degraded-pcap").pcap_degraded is True
    assert controller("degraded-pcap").components()["pcap_store"].status == "degraded"
    assert controller("storm").components()["index"].status == "degraded"
    assert controller("storm").components()["index"].detail


def test_search_decisions_are_deterministic_and_do_not_consume_a_counter() -> None:
    chaos = controller("flaky")
    chaos.decide("fam_a")
    first = chaos.search_decision("fam_a")
    assert first == chaos.search_decision("fam_a")
    assert chaos.counter("fam_a") == 1
    outcomes = []
    for _ in range(60):
        chaos.decide("fam_a", method="POST")
        outcomes.append(chaos.search_decision("fam_a"))
    assert any(d.pre_commit_503 for d in outcomes)
    assert any(d.post_commit_503 for d in outcomes)
    assert all(not d.fail_during_scan for d in outcomes)


def test_storm_can_fail_a_search_during_the_scan() -> None:
    chaos = controller("storm")
    seen = []
    for _ in range(400):
        chaos.decide("fam_a", method="POST")
        seen.append(chaos.search_decision("fam_a").fail_during_scan)
    assert any(seen)


@pytest.mark.parametrize(
    "path",
    [
        "/v1/health",
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/__admin/chaos",
        "/v1/__observer/report",
        "/__observer",
        "/v1/stream/detections",
        "/v1/live",
        "/v1/live/tickets",
        "/openapi.json",
        "/docs",
    ],
)
def test_exempt_paths(path: str) -> None:
    assert is_exempt(path) is True


@pytest.mark.parametrize(
    "path", ["/v1/me", "/v1/sessions/1", "/v1/searches", "/v1/detections", "/v1/estimate"]
)
def test_faultable_paths(path: str) -> None:
    assert is_exempt(path) is False


def test_middleware_faults_a_get_but_never_health(make_client: ClientFactory) -> None:
    client = make_client(chaos="storm")
    client.put(
        "/v1/__admin/chaos",
        headers=ADMIN_HEADERS,
        json={"profile": "storm", "overrides": {"get_503_rate": 1.0, "latency_ms": [0, 0]}},
    )
    response = client.get("/v1/me")
    assert response.status_code == 503
    assert response.json()["code"] == "unavailable"
    assert int(response.headers["retry-after"]) >= 1
    assert client.get("/v1/health").status_code == 200
    login = client.post("/v1/auth/login", json={"email": "x@y.example", "password": "no"})
    assert login.status_code == 401


def test_middleware_leaves_calm_requests_alone(make_client: ClientFactory) -> None:
    client = make_client()
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/health").json()["status"] == "ok"


async def test_drop_sends_a_partial_body_then_aborts() -> None:
    chaos = controller("storm")
    chaos.configure("storm", ChaosOverrides(get_503_rate=0.0, drop_rate=1.0, latency_ms=(0, 0)))
    sent: list[Message] = []

    async def receive() -> Message:  # pragma: no cover - never awaited
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    async def inner(scope: Scope, _receive: Any, _send: Any) -> None:  # pragma: no cover
        raise AssertionError("a dropped request must never reach the app")

    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/sessions/1",
        "headers": [],
        "client": ("127.0.0.1", 5000),
        "app": SimpleNamespace(state=SimpleNamespace(chaos=chaos)),
        "state": {},
    }
    with pytest.raises(ChaosDroppedConnection):
        await ChaosMiddleware(inner)(scope, receive, send)
    start, body = sent
    promised = next(int(v) for k, v in start["headers"] if k == b"content-length")
    assert start["status"] == 200
    assert promised > len(body["body"])
    assert body["more_body"] is True


async def test_middleware_ignores_websocket_and_lifespan_scopes() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, _receive: Any, _send: Any) -> None:
        seen.append(str(scope["type"]))

    async def receive() -> Message:  # pragma: no cover - never awaited
        return {"type": "websocket.connect"}

    async def send(_message: Message) -> None:  # pragma: no cover - never called
        return None

    middleware = ChaosMiddleware(inner)
    for kind in ("websocket", "lifespan"):
        await middleware({"type": kind}, receive, send)
    assert seen == ["websocket", "lifespan"]


def test_the_chaos_key_is_the_family_when_there_is_one(make_client: ClientFactory) -> None:
    client: TestClient = make_client()
    chaos: ChaosController = client.app.state.chaos  # type: ignore[attr-defined]
    client.get("/v1/me")
    assert chaos.counter("ip:testclient") == 1
    body = client.post(
        "/v1/auth/login", json={"email": "ana@quillmere.example", "password": "demo-analyst"}
    ).json()
    client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert chaos.counter("ip:testclient") == 1
