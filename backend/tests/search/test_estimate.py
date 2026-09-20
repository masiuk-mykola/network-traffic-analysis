from datetime import timedelta

import httpx2
from fastapi.testclient import TestClient

from capture_api.domain.base import iso_ms
from capture_api.settings import Settings


def estimate(
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
    return client.get("/v1/estimate", headers=headers, params=query)


def test_estimates_a_filtered_window(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, headers, window, sensors="hq-core", f=["protocol:eq:dns"])
    body = response.json()
    assert response.status_code == 200
    assert body["is_estimate"] is True
    assert body["estimated_sessions_scanned"] > 0
    assert 0 < body["estimated_matches"] <= body["estimated_sessions_scanned"]


def test_an_impossible_filter_estimates_zero(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(
        client, headers, window, sensors="hq-core", f=["dst.port:eq:9", "protocol:eq:ntp"]
    )
    assert response.json()["estimated_matches"] == 0


def test_without_sensors_every_readable_sensor_is_scanned(
    client: TestClient,
    headers: dict[str, str],
    observer_headers: dict[str, str],
    window: tuple[str, str],
) -> None:
    everything = estimate(client, headers, window).json()
    partial = estimate(client, observer_headers, window).json()
    assert everything["estimated_sessions_scanned"] > partial["estimated_sessions_scanned"]


def test_an_unreadable_sensor_is_403(
    client: TestClient, observer_headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, observer_headers, window, sensors="dc-east")
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_sensor"


def test_an_unknown_sensor_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, headers, window, sensors="hq-core,nope")
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_sensor"


def test_an_inverted_window_is_400_bad_range(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, headers, (window[1], window[0]), sensors="hq-core")
    assert response.status_code == 400
    assert response.json()["code"] == "bad_range"


def test_a_window_longer_than_a_week_is_400(
    client: TestClient, headers: dict[str, str], settings: Settings
) -> None:
    wide = (iso_ms(settings.epoch - timedelta(days=8)), iso_ms(settings.epoch))
    response = estimate(client, headers, wide, sensors="hq-core")
    assert response.json()["code"] == "bad_range"


def test_a_window_before_the_capture_is_400(
    client: TestClient, headers: dict[str, str], settings: Settings
) -> None:
    old = (iso_ms(settings.epoch - timedelta(days=10)), iso_ms(settings.epoch - timedelta(days=9)))
    response = estimate(client, headers, old, sensors="hq-core")
    assert response.json()["code"] == "bad_range"


def test_an_unparseable_filter_row_is_400_with_its_index(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, headers, window, f=["protocol:eq:dns", "nonsense"])
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "bad_filter_param"
    assert body["row_index"] == 1


def test_an_unknown_field_is_422_with_its_index(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = estimate(client, headers, window, f=["nope:eq:1"])
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unknown_field"
    assert body["row_index"] == 0


def test_five_estimates_a_second_is_one_too_many(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    for _ in range(4):
        assert estimate(client, headers, window, sensors="hq-core").status_code == 200
    response = estimate(client, headers, window, sensors="hq-core")
    assert response.status_code == 429
    assert response.json()["code"] == "estimate_rate_limited"
    assert response.headers["Retry-After"] == "1"
