from datetime import timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.domain.base import from_epoch_ms, iso_ms
from capture_api.platform.chaos import SearchDecision
from capture_api.search.jobs import MAX_LIMIT, SearchService, scan_duration_s
from capture_api.world.clock import FakeTimeSource
from capture_api.world.types import World
from tests.conftest import ANALYST, do_login
from tests.search.conftest import create_search, search_body, wait_done


def service(client: TestClient) -> SearchService:
    app: FastAPI = client.app  # type: ignore[assignment]
    return cast(SearchService, app.state.searches)


def test_creating_a_search_answers_202_with_a_location(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post("/v1/searches", headers=headers, json=search_body(window))
    assert response.status_code == 202
    body = response.json()
    assert body["state"] in ("queued", "running")
    assert response.headers["Location"] == f"/v1/searches/{body['id']}"
    assert body["progress"]["matched_is_estimate"] is True


def test_a_search_finishes_and_reports_its_totals(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    done = wait_done(client, headers, created["id"])
    assert done["state"] == "done"
    assert done["progress"]["matched_is_estimate"] is False
    assert done["progress"]["percent"] == 100.0
    assert done["progress"]["matched"] > 0
    assert done["stats"]["matched_bytes_up"] > 0
    assert done["finished_at"]


def test_results_are_paged_in_scan_order(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    first = client.get(
        f"/v1/searches/{created['id']}/results", headers=headers, params={"limit": 5}
    )
    page = first.json()
    assert len(page["items"]) == 5
    assert page["next_cursor"]
    assert page["complete"] is False
    starts = [item["start"] for item in page["items"]]
    assert starts == sorted(starts, reverse=True)

    second = client.get(
        f"/v1/searches/{created['id']}/results",
        headers=headers,
        params={"limit": 5, "cursor": page["next_cursor"]},
    ).json()
    assert second["items"][0]["id"] != page["items"][0]["id"]


def test_the_last_page_is_complete(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(
        client, headers, window, filter={"field": "protocol", "op": "eq", "value": "ntp"}
    )
    done = wait_done(client, headers, created["id"])
    page = client.get(f"/v1/searches/{created['id']}/results", headers=headers).json()
    assert page["next_cursor"] is None
    assert page["complete"] is True
    assert page["matched_so_far"] == done["progress"]["matched"]


def test_limit_is_clamped_and_reported_in_a_header(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    response = client.get(
        f"/v1/searches/{created['id']}/results", headers=headers, params={"limit": 900}
    )
    assert response.status_code == 200
    assert response.headers["X-Limit-Applied"] == str(MAX_LIMIT)
    assert len(response.json()["items"]) <= MAX_LIMIT

    default = client.get(f"/v1/searches/{created['id']}/results", headers=headers)
    assert default.headers["X-Limit-Applied"] == "200"


def test_a_tampered_cursor_is_400(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    response = client.get(
        f"/v1/searches/{created['id']}/results", headers=headers, params={"cursor": "nope.nope"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


def test_a_cursor_of_another_sort_is_400(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    sorted_page = client.get(
        f"/v1/searches/{created['id']}/results",
        headers=headers,
        params={"limit": 5, "sort": "-bytes"},
    ).json()
    response = client.get(
        f"/v1/searches/{created['id']}/results",
        headers=headers,
        params={"limit": 5, "cursor": sorted_page["next_cursor"]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "cursor_sort_mismatch"


def test_sorting_by_bytes_once_done(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    items = client.get(
        f"/v1/searches/{created['id']}/results",
        headers=headers,
        params={"limit": 20, "sort": "-bytes"},
    ).json()["items"]
    totals = [item["bytes"]["up"] + item["bytes"]["down"] for item in items]
    assert totals == sorted(totals, reverse=True)


def test_deleting_a_search_always_answers_204(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    assert client.delete(f"/v1/searches/{created['id']}", headers=headers).status_code == 204
    assert client.delete(f"/v1/searches/{created['id']}", headers=headers).status_code == 204
    assert client.delete("/v1/searches/srch_nothing", headers=headers).status_code == 204
    assert client.get(f"/v1/searches/{created['id']}", headers=headers).status_code == 404


def test_an_unknown_search_is_404(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/v1/searches/srch_nothing", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "search_not_found"


def test_another_users_search_is_404(
    client: TestClient,
    headers: dict[str, str],
    observer_headers: dict[str, str],
    window: tuple[str, str],
) -> None:
    created = create_search(client, headers, window)
    assert client.get(f"/v1/searches/{created['id']}", headers=observer_headers).status_code == 404


def test_an_idle_search_expires_with_410_and_frees_its_slot(
    client: TestClient,
    headers: dict[str, str],
    window: tuple[str, str],
    fake_time: FakeTimeSource,
) -> None:
    created = create_search(client, headers, window)
    wait_done(client, headers, created["id"])
    fake_time.advance(601)
    fresh = do_login(client, *ANALYST).headers
    response = client.get(f"/v1/searches/{created['id']}", headers=fresh)
    assert response.status_code == 410
    assert response.json()["code"] == "search_expired"
    assert service(client).active_count() == 0
    assert client.post("/v1/searches", headers=fresh, json=search_body(window)).status_code == 202


def test_a_fourth_concurrent_search_is_429(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    ids = [create_search(client, headers, window)["id"] for _ in range(3)]
    response = client.post("/v1/searches", headers=headers, json=search_body(window))
    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "too_many_searches"
    assert body["active"] == 3
    assert response.headers["Retry-After"] == "5"

    assert client.delete(f"/v1/searches/{ids[0]}", headers=headers).status_code == 204
    assert client.post("/v1/searches", headers=headers, json=search_body(window)).status_code == 202


def test_a_done_search_still_holds_its_slot(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    for _ in range(3):
        created = create_search(client, headers, window)
        wait_done(client, headers, created["id"])
    assert client.post("/v1/searches", headers=headers, json=search_body(window)).status_code == 429


def test_an_unknown_sensor_is_422_with_a_loc(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post(
        "/v1/searches", headers=headers, json=search_body(window, sensor_ids=["hq-core", "nope"])
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "unknown_sensor"
    assert body["loc"] == ["body", "sensor_ids", 1]


def test_an_unreadable_sensor_is_403(
    client: TestClient, observer_headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post(
        "/v1/searches", headers=observer_headers, json=search_body(window, sensor_ids=["dc-east"])
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_sensor"


def test_a_bad_filter_is_422_with_a_loc_into_the_filter(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    body = search_body(
        window, filter={"all": [{"not": {"field": "nope", "op": "eq", "value": "x"}}]}
    )
    response = client.post("/v1/searches", headers=headers, json=body)
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_field"
    assert response.json()["loc"] == ["body", "filter", "all", 0, "not"]


def test_an_operator_the_field_forbids_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    body = search_body(window, filter={"field": "protocol", "op": "glob", "value": "t*"})
    response = client.post("/v1/searches", headers=headers, json=body)
    assert response.json()["code"] == "operator_not_allowed"


def test_an_inverted_window_is_400(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post(
        "/v1/searches",
        headers=headers,
        json=search_body(window, **{"from": window[1], "to": window[0]}),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_range"


def test_more_than_five_sensors_is_a_request_validation_error(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post(
        "/v1/searches", headers=headers, json=search_body(window, sensor_ids=["hq-core"] * 6)
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_the_same_key_and_body_replays_the_same_search(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    key = {"Idempotency-Key": "search-key-0001", **headers}
    first = client.post("/v1/searches", headers=key, json=search_body(window))
    assert first.status_code == 202
    second = client.post("/v1/searches", headers=key, json=search_body(window))
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert service(client).active_count() == 1


def test_the_same_key_with_another_body_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    key = {"Idempotency-Key": "search-key-0002", **headers}
    client.post("/v1/searches", headers=key, json=search_body(window))
    response = client.post("/v1/searches", headers=key, json=search_body(window, sort="-bytes"))
    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_mismatch"


def test_a_malformed_key_is_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    response = client.post(
        "/v1/searches", headers={"Idempotency-Key": "short", **headers}, json=search_body(window)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_idempotency_key"


def test_a_post_commit_503_is_replayed_by_the_same_key(
    client: TestClient,
    headers: dict[str, str],
    window: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]
    decision = SearchDecision(
        pre_commit_503=False, post_commit_503=True, fail_during_scan=False, retry_after_s=2
    )
    monkeypatch.setattr(app.state.chaos, "search_decision", lambda _request: decision)
    key = {"Idempotency-Key": "search-key-0003", **headers}
    first = client.post("/v1/searches", headers=key, json=search_body(window))
    assert first.status_code == 503
    assert first.json()["code"] == "unavailable"

    monkeypatch.undo()
    retry = client.post("/v1/searches", headers=key, json=search_body(window))
    assert retry.status_code == 200
    assert retry.headers["Idempotent-Replayed"] == "true"
    assert service(client).active_count() == 1


def test_a_pre_commit_503_creates_nothing(
    client: TestClient,
    headers: dict[str, str],
    window: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]
    decision = SearchDecision(
        pre_commit_503=True, post_commit_503=False, fail_during_scan=False, retry_after_s=3
    )
    monkeypatch.setattr(app.state.chaos, "search_decision", lambda _request: decision)
    response = client.post("/v1/searches", headers=headers, json=search_body(window))
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "3"
    assert service(client).active_count() == 0


def test_chaos_can_fail_a_scan(
    client: TestClient,
    headers: dict[str, str],
    window: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app: FastAPI = client.app  # type: ignore[assignment]
    decision = SearchDecision(
        pre_commit_503=False, post_commit_503=False, fail_during_scan=True, retry_after_s=1
    )
    monkeypatch.setattr(app.state.chaos, "search_decision", lambda _request: decision)
    created = create_search(
        client, headers, window, filter={"field": "protocol", "op": "eq", "value": "ntp"}
    )
    assert wait_done(client, headers, created["id"])["state"] == "failed"
    page = client.get(f"/v1/searches/{created['id']}/results", headers=headers).json()
    assert page["next_cursor"] is None
    assert page["complete"] is True


def test_a_window_over_the_capture_gap_warns(
    client: TestClient, headers: dict[str, str], world: World
) -> None:
    incident = world.incident()
    from_iso = iso_ms(from_epoch_ms(incident.capture_gap_start_ms) - timedelta(minutes=30))
    to_iso = iso_ms(from_epoch_ms(incident.capture_gap_end_ms) + timedelta(minutes=30))
    created = create_search(
        client,
        headers,
        (from_iso, to_iso),
        sensor_ids=["harbor-branch"],
        filter={"all": []},
    )
    codes = [warning["code"] for warning in created["warnings"]]
    assert "capture_gap" in codes
    gap = next(w for w in created["warnings"] if w["code"] == "capture_gap")
    assert gap["sensor_id"] == "harbor-branch"
    assert gap["from"] < gap["to"]


def test_a_window_reaching_the_live_tail_warns_about_the_lagging_sensor(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(
        client, headers, window, sensor_ids=["harbor-branch"], filter={"all": []}
    )
    assert any(w["code"] == "sensor_lagging" for w in created["warnings"])


def test_hq_core_alone_raises_no_warning(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    created = create_search(client, headers, window)
    assert created["warnings"] == []


def test_a_running_search_refuses_another_ordering(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    service(client).paced = True
    created = create_search(client, headers, window)
    try:
        response = client.get(
            f"/v1/searches/{created['id']}/results", headers=headers, params={"sort": "bytes"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "search_running"

        caught_up = client.get(f"/v1/searches/{created['id']}/results", headers=headers).json()
        assert caught_up["complete"] is False
        assert caught_up["next_cursor"] is None or caught_up["items"]
    finally:
        client.delete(f"/v1/searches/{created['id']}", headers=headers)


def test_the_scan_duration_is_clamped() -> None:
    assert scan_duration_s(0) == 3.0
    assert scan_duration_s(12_000) == 3.0
    assert scan_duration_s(120_000) == 10.0
    assert scan_duration_s(10_000_000) == 20.0
