import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.main import MIDDLEWARE_PROVIDERS, SERVICE_PROVIDERS, create_app
from capture_api.platform.chaos import ChaosMiddleware
from capture_api.platform.observer import ObserverMiddleware
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource

LANDED_SERVICES = (
    "capture_api.world.world",
    "capture_api.platform.ratelimit",
    "capture_api.platform.idempotency",
    "capture_api.platform.chaos",
    "capture_api.platform.observer",
)
STATE_ATTRIBUTES = ("world", "rate_limiter", "idempotency", "chaos", "observer")


def test_every_landed_service_is_listed_and_has_a_lifespan() -> None:
    for name in LANDED_SERVICES:
        assert name in SERVICE_PROVIDERS, name
        module = importlib.import_module(name)
        assert hasattr(module, "lifespan"), name


def test_the_lifespan_puts_every_landed_service_on_app_state(client: TestClient) -> None:
    for attribute in STATE_ATTRIBUTES:
        assert getattr(client.app.state, attribute, None) is not None, attribute


def test_both_middlewares_are_installed_with_the_observer_outermost(app: FastAPI) -> None:
    classes = [middleware.cls for middleware in app.user_middleware]
    assert ChaosMiddleware in classes
    assert ObserverMiddleware in classes
    assert classes.index(ObserverMiddleware) < classes.index(ChaosMiddleware)
    assert len(MIDDLEWARE_PROVIDERS) == 2


def test_health_is_always_200_and_names_every_component(client: TestClient) -> None:
    body = client.get("/v1/health").json()
    assert set(body["components"]) == {"index", "decoder", "pcap_store", "live_feed"}
    assert body["status"] in {"ok", "degraded"}
    assert body["server_time"].endswith("Z")


def test_health_stays_200_under_the_storm_profile(client: TestClient) -> None:
    headers = {"X-Admin-Token": "lf-dev-admin"}
    put = client.put("/v1/__admin/chaos", json={"profile": "storm"}, headers=headers)
    assert put.status_code == 200, put.text
    body = client.get("/v1/health").json()
    assert body["status"] == "degraded"
    assert body["components"]["index"]["status"] == "degraded"


def test_the_observer_records_traffic_through_the_middleware(client: TestClient) -> None:
    client.post(
        "/v1/auth/login", json={"email": "ana@quillmere.example", "password": "demo-analyst"}
    )
    report = client.get("/v1/__observer/report", headers={"X-Admin-Token": "lf-dev-admin"}).json()
    assert report["families"]
    assert sum(family["requests"] for family in report["families"]) > 0
    assert set(report["summary"]) == {"pass", "warn", "fail"}


@pytest.mark.parametrize("profile", ["calm", "flaky", "storm", "degraded-pcap", "expiring-tokens"])
def test_every_chaos_profile_boots(profile: str) -> None:
    settings = Settings(_env_file=None, seed="test", chaos=profile, teammate_bot=False)
    with TestClient(create_app(settings, time_source=FakeTimeSource())) as client:
        assert client.get("/v1/health").status_code == 200
