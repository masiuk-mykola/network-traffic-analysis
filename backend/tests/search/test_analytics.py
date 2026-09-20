from datetime import timedelta

import httpx2
from fastapi.testclient import TestClient

from capture_api.domain.base import from_epoch_ms, iso_ms
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource
from capture_api.world.types import World
from tests.conftest import ANALYST, do_login
from tests.search.conftest import create_search, wait_done


def get_histogram(
    client: TestClient, headers: dict[str, str], window: tuple[str, str], **params: object
) -> httpx2.Response:
    query: list[tuple[str, str | int | float | bool | None]] = [
        ("from", window[0]),
        ("to", window[1]),
    ]
    for key, value in params.items():
        if isinstance(value, list):
            query.extend((key, str(item)) for item in value)
        else:
            query.append((key, str(value)))
    return client.get("/v1/histogram", headers=headers, params=query)


def test_lql_parse_returns_a_filter_and_its_canonical_form(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(
        "/v1/lql/parse", headers=headers, json={"q": "PROTOCOL = tls AND has tls.sni"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["normalized"] == "protocol = tls and has tls.sni"
    assert body["filter"]["all"][0] == {"field": "protocol", "op": "eq", "value": "tls"}


def test_lql_parse_reports_the_error_span(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/v1/lql/parse", headers=headers, json={"q": "protocol = "})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "lql_syntax"
    assert body["ctx"] == {"pos": 11, "end": 12}


def test_lql_parse_output_is_accepted_by_the_search(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    parsed = client.post(
        "/v1/lql/parse", headers=headers, json={"q": "protocol = dns and dns.rcode = NXDOMAIN"}
    ).json()
    created = create_search(client, headers, window, filter=parsed["filter"])
    assert wait_done(client, headers, created["id"])["state"] == "done"


def test_histogram_counts_sessions_per_protocol(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = get_histogram(client, headers, window, sensors="hq-core", bucket_s=900)
    assert response.status_code == 200
    body = response.json()
    assert body["bucket_s"] == 900
    assert len(body["buckets"]) == 8
    first = body["buckets"][0]
    assert first["coverage"] == 1.0
    assert first["by_protocol"]["dns"] > 0
    assert first["bytes"] > 0
    assert "partial" not in first


def test_histogram_honours_the_filter(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    body = get_histogram(
        client, headers, window, sensors="hq-core", bucket_s=1800, f=["protocol:eq:dns"]
    ).json()
    assert all(set(bucket["by_protocol"]) <= {"dns"} for bucket in body["buckets"])


def test_buckets_with_no_capture_are_omitted_not_zero(
    client: TestClient, headers: dict[str, str], world: World
) -> None:
    incident = world.incident()
    start = from_epoch_ms(incident.capture_gap_start_ms)
    end = from_epoch_ms(incident.capture_gap_end_ms)
    window = (
        iso_ms(start - timedelta(hours=1, seconds=30)),
        iso_ms(end + timedelta(hours=1)),
    )
    body = get_histogram(client, headers, window, sensors="harbor-branch", bucket_s=60).json()
    times = {bucket["t"] for bucket in body["buckets"]}
    inside = iso_ms(start + timedelta(minutes=5))
    assert inside not in times
    assert len(times) < 140
    straddling = [bucket for bucket in body["buckets"] if bucket["coverage"] < 1.0]
    assert straddling, "the buckets at the edges of the gap are only partly covered"


def test_the_bucket_holding_the_capture_clock_is_partial(
    client: TestClient, settings: Settings, fake_time: FakeTimeSource, world: World
) -> None:
    fake_time.advance(120)
    headers = do_login(client, *ANALYST).headers
    window = (
        iso_ms(settings.epoch - timedelta(hours=1)),
        iso_ms(settings.epoch + timedelta(hours=1)),
    )
    body = get_histogram(client, headers, window, sensors="hq-core", bucket_s=3600).json()
    assert body["buckets"][-1]["partial"] is True
    assert body["buckets"][-1]["coverage"] < 1.0


def test_too_many_buckets_is_400(
    client: TestClient, headers: dict[str, str], settings: Settings
) -> None:
    window = (iso_ms(settings.epoch - timedelta(days=3)), iso_ms(settings.epoch))
    response = get_histogram(client, headers, window, bucket_s=60)
    assert response.status_code == 400
    assert response.json()["code"] == "bad_range"


def test_a_bucket_outside_the_allowed_range_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    assert get_histogram(client, headers, window, bucket_s=30).status_code == 422
    assert get_histogram(client, headers, window, bucket_s=90_000).status_code == 422


def test_histogram_and_pivot_share_one_rate_limit(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    for _ in range(9):
        assert get_histogram(client, headers, window, sensors="hq-core").status_code == 200
    pivot = client.get(
        "/v1/pivot/occurrences",
        headers=headers,
        params={
            "from": window[0],
            "to": window[1],
            "field": "protocol",
            "value": "dns",
            "sensors": "hq-core",
        },
    )
    assert pivot.status_code == 200
    response = get_histogram(client, headers, window, sensors="hq-core")
    assert response.status_code == 429
    assert response.json()["code"] == "analytics_rate_limited"


def test_pivot_counts_occurrences_per_sensor(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.get(
        "/v1/pivot/occurrences",
        headers=headers,
        params={
            "from": window[0],
            "to": window[1],
            "field": "protocol",
            "value": "dns",
            "bucket_s": 1800,
            "sensors": "hq-core,dc-east",
        },
    )
    assert response.status_code == 200
    series = response.json()["series"]
    assert [item["sensor_id"] for item in series] == ["hq-core", "dc-east"]
    assert all(bucket["count"] > 0 for item in series for bucket in item["buckets"])


def test_pivot_on_an_unknown_field_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.get(
        "/v1/pivot/occurrences",
        headers=headers,
        params={"from": window[0], "to": window[1], "field": "nope", "value": "x"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_field"


def test_the_conversation_graph_of_a_finished_search(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    body = client.get(
        f"/v1/searches/{created['id']}/graph", headers=headers, params={"limit_nodes": 10}
    ).json()
    assert 0 < len(body["nodes"]) <= 10
    assert body["nodes"][0]["bytes"] >= body["nodes"][-1]["bytes"]
    assert {node["kind"] for node in body["nodes"]} <= {"internal", "external"}
    assert all(
        edge["a"] in {node["id"] for node in body["nodes"]}
        and edge["b"] in {node["id"] for node in body["nodes"]}
        for edge in body["edges"]
    )
    assert body["partial"] is True


def test_a_complete_graph_is_not_partial(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(
        client, headers, window, filter={"field": "protocol", "op": "eq", "value": "ntp"}
    )
    wait_done(client, headers, created["id"])
    body = client.get(
        f"/v1/searches/{created['id']}/graph", headers=headers, params={"limit_nodes": 500}
    ).json()
    assert body["partial"] is False


def test_the_graph_of_an_unknown_search_is_404(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get("/v1/searches/srch_nothing/graph", headers=headers).status_code == 404
