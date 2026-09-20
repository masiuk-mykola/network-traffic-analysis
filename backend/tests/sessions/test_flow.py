from collections.abc import Callable
from itertools import pairwise

from fastapi.testclient import TestClient

from tests.conftest import OBSERVER, LoggedIn

from .conftest import Catalog


def test_samples_are_ascending_and_never_empty(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.long_session

    response = client.get(f"/v1/sessions/{row.id}/flow", headers=login().headers)

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == str(row.id)
    assert body["bucket_ms"] == 1000
    samples = body["samples"]
    assert samples
    assert [sample["t"] for sample in samples] == sorted(sample["t"] for sample in samples)
    for sample in samples:
        assert isinstance(sample["t"], int), "flow timestamps are epoch ms, not ISO strings"
        assert sample["bytes_up"] + sample["bytes_down"] > 0
        assert row.start_ms <= sample["t"] <= row.end_ms


def test_empty_buckets_are_omitted_from_a_long_session(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.long_session

    samples = client.get(
        f"/v1/sessions/{row.id}/flow?bucket_ms=1000", headers=login().headers
    ).json()["samples"]

    span_buckets = row.duration_ms // 1000 + 1
    assert len(samples) < span_buckets, "an idle gap must be a missing sample, not a zero"
    gaps = [later["t"] - earlier["t"] for earlier, later in pairwise(samples)]
    assert max(gaps) > 1000


def test_totals_stay_close_to_the_row(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.long_session

    samples = client.get(f"/v1/sessions/{row.id}/flow", headers=login().headers).json()["samples"]

    assert sum(sample["bytes_up"] for sample in samples) == row.bytes_up
    assert sum(sample["bytes_down"] for sample in samples) == row.bytes_down


def test_the_bucket_width_is_bounded(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    session_id = rows.long_session.id
    headers = login().headers

    for good in (100, 1000, 60_000):
        response = client.get(f"/v1/sessions/{session_id}/flow?bucket_ms={good}", headers=headers)
        assert response.status_code == 200, good
        assert response.json()["bucket_ms"] == good
    for bad in (99, 0, -1, 60_001, 1_000_000):
        response = client.get(f"/v1/sessions/{session_id}/flow?bucket_ms={bad}", headers=headers)
        assert response.status_code == 422, bad
        assert response.json()["detail"][0]["loc"] == ["query", "bucket_ms"]


def test_works_after_the_pcap_expired(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.pcap_expired
    headers = login().headers

    detail = client.get(f"/v1/sessions/{row.id}", headers=headers).json()
    flow = client.get(f"/v1/sessions/{row.id}/flow", headers=headers)

    assert detail["pcap"]["available"] is False
    assert flow.status_code == 200
    assert flow.json()["samples"]


def test_404_and_403_match_the_detail_route(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    assert client.get("/v1/sessions/nope/flow", headers=login().headers).status_code == 404
    forbidden = client.get(f"/v1/sessions/{rows.dc_east.id}/flow", headers=login(*OBSERVER).headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden_sensor"
