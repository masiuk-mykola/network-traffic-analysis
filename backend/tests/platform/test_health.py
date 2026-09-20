from capture_api import __version__
from capture_api.world.clock import FakeTimeSource

from .conftest import ADMIN_HEADERS, ClientFactory

COMPONENTS = {"index", "decoder", "pcap_store", "live_feed"}


def test_health_needs_no_authentication_and_is_always_200(make_client: ClientFactory) -> None:
    response = make_client().get("/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == COMPONENTS
    assert body["version"] == __version__
    assert body["server_time"].endswith("Z")
    assert all(component["status"] == "ok" for component in body["components"].values())
    assert "detail" not in body["components"]["index"]


def test_server_time_is_the_capture_clock(
    make_client: ClientFactory, fake_time: FakeTimeSource
) -> None:
    client = make_client()
    first = client.get("/v1/health").json()["server_time"]
    fake_time.advance(3600)
    second = client.get("/v1/health").json()["server_time"]
    assert second > first
    assert first.startswith("2025-10-27T12:00:00")


def test_degraded_pcap_only_degrades_the_packet_store(make_client: ClientFactory) -> None:
    body = make_client(chaos="degraded-pcap").get("/v1/health").json()
    assert body["status"] == "degraded"
    assert body["components"]["pcap_store"]["status"] == "degraded"
    assert body["components"]["pcap_store"]["detail"]
    assert body["components"]["index"]["status"] == "ok"


def test_storm_degrades_the_index(make_client: ClientFactory) -> None:
    body = make_client(chaos="storm").get("/v1/health").json()
    assert body["status"] == "degraded"
    assert body["components"]["index"]["status"] == "degraded"


def test_switching_the_profile_changes_health_live(make_client: ClientFactory) -> None:
    client = make_client()
    assert client.get("/v1/health").json()["status"] == "ok"
    client.put(
        "/v1/__admin/chaos", headers=ADMIN_HEADERS, json={"profile": "degraded-pcap"}
    ).raise_for_status()
    assert client.get("/v1/health").json()["components"]["pcap_store"]["status"] == "degraded"


def test_health_is_documented_in_the_schema(make_client: ClientFactory) -> None:
    schema = make_client().get("/openapi.json").json()
    assert "/v1/health" in schema["paths"]
    assert schema["paths"]["/v1/health"]["get"]["operationId"] == "getHealth"
