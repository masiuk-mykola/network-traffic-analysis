from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from capture_api.api.observer import CHECKS, build_report, render_report_html
from capture_api.domain.base import iso_ms
from capture_api.domain.models import ObserverCheck
from capture_api.platform.observer import Observer, RequestRecord
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource

from .conftest import ADMIN_HEADERS, ClientFactory

BASE_MONO = 1000.0
BASE_WALL = 1_761_566_400.0
FAMILY = "fam_a"
USER = "ana@quillmere.example"
HUNT = "/v1/hunts/hnt_1"


def _iso(offset: float) -> str:
    return iso_ms(datetime.fromtimestamp(BASE_WALL + offset, tz=UTC))


class Traffic:
    def __init__(self, observer: Observer, clock: FakeTimeSource) -> None:
        self.observer = observer
        self.clock = clock
        self.seq = 0

    def wait(self, seconds: float) -> None:
        self.clock.advance(seconds)

    def add(self, t: float, **fields: Any) -> RequestRecord:
        self.seq += 1
        path = fields.pop("path", "/v1/sessions/72075232438042624")
        defaults: dict[str, Any] = {
            "method": "GET",
            "route": fields.pop("route", path),
            "query": "",
            "query_hash": "q",
            "status": 200,
            "duration_ms": 1.0,
            "has_authorization": True,
        }
        defaults.update(fields)
        record = RequestRecord(
            seq=self.seq,
            t_mono=BASE_MONO + t,
            t_iso=_iso(t),
            family_id=FAMILY,
            user=USER,
            path=path,
            **defaults,
        )
        return self.observer.record(record)


type Builder = Callable[[Traffic], None]


def evaluate(build: Builder) -> dict[str, ObserverCheck]:
    clock = FakeTimeSource(wall=BASE_WALL, monotonic=BASE_MONO)
    observer = Observer(clock, seed="test")
    build(Traffic(observer, clock))
    clock.advance(300)
    report = build_report(observer, Settings(_env_file=None, seed="test"), profile="calm")
    assert len(report.families) == 1
    return {check.id: check for check in report.families[0].checks}


def refresh_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/auth/refresh", has_authorization=False)
    t.add(90, method="POST", path="/v1/auth/refresh", has_authorization=False)


def refresh_stampede(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/auth/refresh", has_authorization=False)
    t.add(0.3, method="POST", path="/v1/auth/refresh", has_authorization=False)


def reuse_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/auth/refresh", has_authorization=False)


def reuse_bad(t: Traffic) -> None:
    reuse_ok(t)
    t.add(
        5,
        method="POST",
        path="/v1/auth/refresh",
        status=401,
        error_code="refresh_reused",
        has_authorization=False,
    )


def logout_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/auth/logout", status=204)
    t.add(1, path="/v1/me")


def logout_bad(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/auth/logout", status=204)
    t.add(30, path="/v1/me", status=401, error_code="session_revoked")


def origin_ok(t: Traffic) -> None:
    t.add(0, path="/v1/me", origin="http://localhost:3000", has_authorization=False)


def origin_bad(t: Traffic) -> None:
    t.add(0, path="/v1/me", origin="http://localhost:3000", has_authorization=True)


def searches_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/searches", status=202, body_hash="a", resource_id="srch_1")
    t.add(1, method="DELETE", path="/v1/searches/srch_1", status=204)
    t.add(2, method="POST", path="/v1/searches", status=202, body_hash="b", resource_id="srch_2")
    t.add(3, method="DELETE", path="/v1/searches/srch_2", status=204)


def searches_duplicated(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/searches", status=202, body_hash="a", resource_id="srch_1")
    t.add(1, method="POST", path="/v1/searches", status=202, body_hash="a", resource_id="srch_2")
    t.add(2, method="DELETE", path="/v1/searches/srch_1", status=204)
    t.add(3, method="DELETE", path="/v1/searches/srch_2", status=204)


def searches_abandoned(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/searches", status=202, body_hash="a", resource_id="srch_1")
    t.add(5, method="POST", path="/v1/searches", status=202, body_hash="b", resource_id="srch_2")


def slots_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/searches", status=202, body_hash="a", resource_id="srch_1")


def slots_exhausted(t: Traffic) -> None:
    slots_ok(t)
    t.add(1, method="POST", path="/v1/searches", status=429, error_code="too_many_searches")


def retry_after_ok(t: Traffic) -> None:
    t.add(0, path="/v1/detections", status=429, error_code="rate", retry_after_s=2.0)
    t.add(4, path="/v1/detections")


def retry_after_ignored(t: Traffic) -> None:
    t.add(0, path="/v1/detections", status=429, error_code="rate", retry_after_s=2.0)
    t.add(0.5, path="/v1/detections")


def four_xx_ok(t: Traffic) -> None:
    t.add(0, path="/v1/sessions/1", status=404, error_code="session_not_found")
    t.add(30, path="/v1/sessions/1", status=404, error_code="session_not_found")


def four_xx_retried(t: Traffic) -> None:
    t.add(0, path="/v1/sessions/1", status=404, error_code="session_not_found")
    t.add(1, path="/v1/sessions/1", status=404, error_code="session_not_found")


def dedupe_ok(t: Traffic) -> None:
    t.add(0, path="/v1/detections")
    t.add(0.01, path="/v1/detections")


def dedupe_storm(t: Traffic) -> None:
    for index in range(6):
        t.add(index * 0.01, path="/v1/detections")


def cursor_ok(t: Traffic) -> None:
    t.add(0, path="/v1/searches/srch_1/results", query="cursor=abc", query_hash="c")


def cursor_bad(t: Traffic) -> None:
    cursor_ok(t)
    t.add(
        5,
        path="/v1/searches/srch_1/results",
        query="cursor=abc",
        query_hash="c",
        status=400,
        error_code="invalid_cursor",
    )


def limit_ok(t: Traffic) -> None:
    t.add(0, path="/v1/detections", query="limit=200", query_hash="l", limit_param=200)


def limit_over(t: Traffic) -> None:
    t.add(0, path="/v1/detections", query="limit=2000", query_hash="l", limit_param=2000)


def health_calm(t: Traffic) -> None:
    for index in range(4):
        t.add(index * 15, path="/v1/health", has_authorization=False)


def health_hammered(t: Traffic) -> None:
    for index in range(6):
        t.add(index * 1.0, path="/v1/health", has_authorization=False)


def estimate_ok(t: Traffic) -> None:
    t.add(0, path="/v1/estimate", query="f=protocol:eq:dns", query_hash="e")


def estimate_throttled(t: Traffic) -> None:
    estimate_ok(t)
    t.add(0.2, path="/v1/estimate", status=429, error_code="estimate_rate_limited")


def patch_ok(t: Traffic) -> None:
    t.add(0, path=HUNT, resource_fields={"name": "hash-a"})
    t.add(
        1,
        method="PATCH",
        path=HUNT,
        if_match='"v1"',
        body_keys=("name",),
        body_fields={"name": "hash-b"},
    )


def patch_without_if_match(t: Traffic) -> None:
    t.add(0, path=HUNT, resource_fields={"name": "hash-a"})
    t.add(
        1,
        method="PATCH",
        path=HUNT,
        status=428,
        body_keys=("name",),
        body_fields={"name": "hash-b"},
    )


def patch_resends_unchanged(t: Traffic) -> None:
    t.add(0, path=HUNT, resource_fields={"name": "hash-a"})
    t.add(
        1,
        method="PATCH",
        path=HUNT,
        if_match='"v1"',
        body_keys=("name",),
        body_fields={"name": "hash-a"},
    )


def download_ok(t: Traffic) -> None:
    t.add(0, path="/v1/sessions/1/pcap")
    t.add(1, path="/v1/sessions/1/pcap")


def download_storm(t: Traffic) -> None:
    for index in range(4):
        t.add(index * 0.5, path="/v1/sessions/1/pcap")


def enrich_ok(t: Traffic) -> None:
    for index in range(3):
        t.add(index * 0.1, path=f"/v1/enrich/ips/203.0.113.{index}")


def enrich_storm(t: Traffic) -> None:
    for index in range(6):
        t.add(index * 0.1, path=f"/v1/enrich/ips/203.0.113.{index}")


def import_ok(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/imports", status=202)


def import_mismatch(t: Traffic) -> None:
    t.add(0, method="POST", path="/v1/imports", status=422, error_code="checksum_mismatch")


def sse_ok(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.sse_opened(FAMILY, USER)
    t.wait(30)
    t.observer.sse_closed(FAMILY, USER, reason="rotate")
    t.wait(5)
    t.observer.sse_opened(FAMILY, USER, resume_from=120)


def sse_double(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.sse_opened(FAMILY, USER)
    t.wait(0.2)
    t.observer.sse_opened(FAMILY, USER, resume_from=120)


def sse_blind_reopen(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.sse_opened(FAMILY, USER)
    t.wait(30)
    t.observer.sse_closed(FAMILY, USER, reason="rotate")
    t.wait(5)
    t.observer.sse_opened(FAMILY, USER)


def ws_ok(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.ws_opened(FAMILY, USER)
    t.wait(0.4)
    t.observer.ws_subscribed(FAMILY, USER)
    t.wait(15)
    t.observer.ws_pong(FAMILY, USER)
    t.observer.ws_closed(FAMILY, USER, code=1000)


def ws_missed_pong(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.ws_opened(FAMILY, USER)
    t.wait(0.4)
    t.observer.ws_subscribed(FAMILY, USER)
    t.wait(25)
    t.observer.ws_closed(FAMILY, USER, code=4408)


def ws_ticket_reused(t: Traffic) -> None:
    ws_ok(t)
    t.observer.ws_rejected(FAMILY, "ticket_reuse")


def ws_never_subscribes(t: Traffic) -> None:
    t.add(0, path="/v1/health", has_authorization=False)
    t.observer.ws_opened(FAMILY, USER)
    t.wait(30)


SCENARIOS: tuple[tuple[str, Builder, Builder, str], ...] = (
    ("auth.refresh_single_flight", refresh_ok, refresh_stampede, "fail"),
    ("auth.refresh_reuse", reuse_ok, reuse_bad, "fail"),
    ("auth.logout_once", logout_ok, logout_bad, "fail"),
    ("auth.bearer_from_browser", origin_ok, origin_bad, "fail"),
    ("search.duplicate_jobs", searches_ok, searches_duplicated, "fail"),
    ("search.abandoned", searches_ok, searches_abandoned, "fail"),
    ("search.slots_exhausted", slots_ok, slots_exhausted, "fail"),
    ("http.retry_after_violations", retry_after_ok, retry_after_ignored, "fail"),
    ("http.retried_4xx", four_xx_ok, four_xx_retried, "fail"),
    ("http.get_dedupe", dedupe_ok, dedupe_storm, "fail"),
    ("http.invalid_cursor", cursor_ok, cursor_bad, "fail"),
    ("http.limit_over_max", limit_ok, limit_over, "warn"),
    ("poll.health_interval", health_calm, health_hammered, "fail"),
    ("estimate.rate", estimate_ok, estimate_throttled, "fail"),
    ("concurrency.if_match", patch_ok, patch_without_if_match, "fail"),
    ("concurrency.minimal_patch", patch_ok, patch_resends_unchanged, "warn"),
    ("download.single_request", download_ok, download_storm, "fail"),
    ("sse.double_open", sse_ok, sse_double, "fail"),
    ("sse.resume", sse_ok, sse_blind_reopen, "fail"),
    ("sse.reconnect_backoff", sse_ok, sse_double, "n/a"),
    ("ws.pong_ok", ws_ok, ws_missed_pong, "fail"),
    ("ws.ticket_reuse", ws_ok, ws_ticket_reused, "fail"),
    ("ws.resubscribe", ws_ok, ws_never_subscribes, "fail"),
    ("enrich.per_ip_storm", enrich_ok, enrich_storm, "fail"),
    ("import.checksum_mismatch", import_ok, import_mismatch, "fail"),
)


@pytest.mark.parametrize(
    ("check_id", "good", "bad", "bad_status"), SCENARIOS, ids=[row[0] for row in SCENARIOS]
)
def test_each_check_passes_and_fails(
    check_id: str, good: Builder, bad: Builder, bad_status: str
) -> None:
    assert evaluate(good)[check_id].status == "pass"
    if bad_status != "n/a":
        failing = evaluate(bad)[check_id]
        assert failing.status == bad_status
        assert failing.evidence


def test_reconnect_backoff_fails_on_an_immediate_reopen() -> None:
    def build(t: Traffic) -> None:
        t.add(0, path="/v1/health", has_authorization=False)
        t.observer.sse_opened(FAMILY, USER)
        t.wait(30)
        t.observer.sse_closed(FAMILY, USER, reason="rotate")
        t.wait(0.2)
        t.observer.sse_opened(FAMILY, USER, resume_from=12)

    checks = evaluate(build)
    assert checks["sse.reconnect_backoff"].status == "fail"


def test_every_scenario_covers_a_distinct_check() -> None:
    assert {row[0] for row in SCENARIOS} == {spec.id for spec in CHECKS}


def test_checks_are_not_applicable_without_relevant_traffic() -> None:
    def one_call(t: Traffic) -> None:
        t.add(0, path="/v1/me")

    checks = evaluate(one_call)
    assert checks["auth.refresh_reuse"].status == "n/a"
    assert checks["sse.resume"].status == "n/a"
    assert checks["import.checksum_mismatch"].status == "n/a"
    assert checks["http.get_dedupe"].status == "pass"


def test_thresholds_and_values_are_reported() -> None:
    checks = evaluate(dedupe_storm)
    dedupe = checks["http.get_dedupe"]
    assert dedupe.value == 6
    assert dedupe.threshold
    assert dedupe.evidence[0].path.startswith("/v1/detections")


def test_report_summary_counts_every_family() -> None:
    clock = FakeTimeSource(wall=BASE_WALL, monotonic=BASE_MONO)
    observer = Observer(clock, seed="test")
    traffic = Traffic(observer, clock)
    dedupe_storm(traffic)
    searches_ok(traffic)
    report = build_report(observer, Settings(_env_file=None, seed="test"), profile="flaky")
    assert report.profile == "flaky"
    assert report.seed == "test"
    assert report.summary.fail >= 1
    assert report.summary.pass_ >= 1
    assert report.families[0].requests == 10


def test_since_filters_the_window() -> None:
    clock = FakeTimeSource(wall=BASE_WALL, monotonic=BASE_MONO)
    observer = Observer(clock, seed="test")
    traffic = Traffic(observer, clock)
    traffic.add(0, path="/v1/health", has_authorization=False)
    traffic.add(500, path="/v1/health", has_authorization=False)
    clock.advance(600)
    settings = Settings(_env_file=None, seed="test")
    assert build_report(observer, settings, profile="calm").families[0].requests == 2
    windowed = build_report(observer, settings, profile="calm", since="200")
    assert windowed.families[0].requests == 1
    by_iso = build_report(observer, settings, profile="calm", since=_iso(400))
    assert by_iso.families[0].requests == 1


def test_report_route_and_html_page(make_client: ClientFactory) -> None:
    client = make_client()
    client.post(
        "/v1/auth/login", json={"email": USER, "password": "demo-analyst"}
    ).raise_for_status()
    assert client.get("/v1/__observer/report").status_code == 401
    report = client.get("/v1/__observer/report", headers=ADMIN_HEADERS).json()
    assert report["seed"] == "test"
    assert report["profile"] == "calm"
    assert report["full_history"] is False
    assert {"pass", "warn", "fail"} == set(report["summary"])
    assert len(report["families"]) == 1
    assert {check["id"] for check in report["families"][0]["checks"]} == {
        spec.id for spec in CHECKS
    }

    assert client.get("/__observer").status_code == 401
    page = client.get("/__observer", params={"token": "lf-dev-admin"})
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Capture API client-behaviour report" in page.text
    assert "auth.refresh_single_flight" in page.text
    assert "http-equiv='refresh'" in page.text
    assert "<script" not in page.text


def test_report_can_be_filtered_by_family(make_client: ClientFactory) -> None:
    client = make_client()
    client.post("/v1/auth/login", json={"email": USER, "password": "demo-analyst"})
    report = client.get("/v1/__observer/report", headers=ADMIN_HEADERS).json()
    family_id = report["families"][0]["family_id"]
    filtered = client.get(
        "/v1/__observer/report", headers=ADMIN_HEADERS, params={"family_id": family_id}
    ).json()
    assert len(filtered["families"]) == 1
    empty = client.get(
        "/v1/__observer/report", headers=ADMIN_HEADERS, params={"family_id": "fam_nope"}
    ).json()
    assert empty["families"] == []
    assert empty["summary"] == {"pass": 0, "warn": 0, "fail": 0}


def test_a_bad_since_is_rejected(make_client: ClientFactory) -> None:
    response = make_client().get(
        "/v1/__observer/report", headers=ADMIN_HEADERS, params={"since": "last tuesday"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bad_since"


def test_the_html_page_survives_an_empty_report() -> None:
    clock = FakeTimeSource(wall=BASE_WALL, monotonic=BASE_MONO)
    observer = Observer(clock, seed="test")
    report = build_report(observer, Settings(_env_file=None, seed="test"), profile="calm")
    html = render_report_html(report)
    assert "No traffic recorded yet" in html
