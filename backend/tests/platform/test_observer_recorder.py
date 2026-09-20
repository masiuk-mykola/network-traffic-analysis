from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from capture_api.platform.observer import ANONYMOUS, Observer, ObserverMiddleware, route_template
from capture_api.world.clock import FakeTimeSource

from .conftest import ClientFactory

ANALYST = {"email": "ana@quillmere.example", "password": "demo-analyst"}


async def _patch_hunt(request: Request) -> Response:
    await request.json()
    return JSONResponse({"id": "hnt_1", "name": "Beacon hunt", "description": "d"})


async def _get_hunt(_request: Request) -> Response:
    return JSONResponse({"id": "hnt_1", "name": "Beacon hunt", "description": "d"})


async def _boom(_request: Request) -> Response:
    raise RuntimeError("the connection died")


async def _stream(_request: Request) -> Response:
    async def chunks() -> Any:
        yield b"a" * 1024
        yield b"b" * 1024

    return StreamingResponse(chunks(), media_type="application/octet-stream")


@pytest.fixture
def recorder() -> Observer:
    return Observer(FakeTimeSource(), seed="test")


@pytest.fixture
def raw_client(recorder: Observer) -> Iterator[TestClient]:
    app = Starlette(
        routes=[
            Route("/v1/hunts/{hunt_id}", _patch_hunt, methods=["PATCH"]),
            Route("/v1/hunts/{hunt_id}", _get_hunt, methods=["GET"]),
            Route("/v1/boom", _boom),
            Route("/v1/sessions/1/pcap", _stream),
        ]
    )
    app.state.observer = recorder
    app.add_middleware(ObserverMiddleware)
    with TestClient(app) as client:
        yield client


def only(recorder: Observer, index: int = 0) -> Any:
    records = [r for family in recorder.families() for r in family.requests]
    return records[index]


def test_requests_are_attributed_to_the_token_family(make_client: ClientFactory) -> None:
    client = make_client()
    body = client.post("/v1/auth/login", json=ANALYST).json()
    client.get("/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    families = observer.families()
    assert len(families) == 1
    family = families[0]
    assert family.family_id.startswith("fam_")
    assert family.user == "ana@quillmere.example"
    paths = [record.path for record in family.requests]
    assert paths == ["/v1/auth/login", "/v1/me"]
    assert family.requests[-1].has_authorization is True
    assert family.requests[-1].route == "/v1/me"


def test_anonymous_traffic_joins_the_last_family_of_that_client(
    make_client: ClientFactory,
) -> None:
    client = make_client()
    client.post("/v1/auth/login", json=ANALYST)
    client.get("/v1/health")
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    assert len(observer.families()) == 1
    assert observer.families()[0].requests[-1].path == "/v1/health"


def test_traffic_before_any_login_is_anonymous(make_client: ClientFactory) -> None:
    client = make_client()
    client.get("/v1/health")
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    assert observer.families()[0].family_id == ANONYMOUS


def test_error_codes_are_captured(make_client: ClientFactory) -> None:
    client = make_client()
    client.get("/v1/me", headers={"Authorization": "Bearer at_nope"})
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    record = only(observer)
    assert (record.status, record.error_code) == (401, "invalid_token")


def test_tracked_headers_are_recorded(make_client: ClientFactory) -> None:
    client = make_client()
    client.get(
        "/v1/me",
        headers={
            "Origin": "http://localhost:3000",
            "Idempotency-Key": "abcdefgh1234",
            "If-Match": '"v3"',
            "Last-Event-ID": "412",
        },
    )
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    record = only(observer)
    assert record.origin == "http://localhost:3000"
    assert record.idempotency_key == "abcdefgh1234"
    assert record.if_match == '"v3"'
    assert record.last_event_id == "412"


def test_query_is_hashed_and_limit_extracted(make_client: ClientFactory) -> None:
    client = make_client()
    client.get("/v1/me?limit=900&sensors=hq-core")
    client.get("/v1/me?sensors=hq-core&limit=900")
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    first, second = (only(observer, 0), only(observer, 1))
    assert first.limit_param == 900
    assert first.query_hash == second.query_hash


def test_retry_after_is_parsed_from_the_response(make_client: ClientFactory) -> None:
    client = make_client(chaos="storm")
    client.put(
        "/v1/__admin/chaos",
        headers={"X-Admin-Token": "lf-dev-admin"},
        json={"profile": "storm", "overrides": {"get_503_rate": 1.0, "latency_ms": [0, 0]}},
    )
    client.get("/v1/me")
    observer: Observer = client.app.state.observer  # type: ignore[attr-defined]
    faulted = next(r for f in observer.families() for r in f.requests if r.status == 503)
    assert faulted.retry_after_s is not None
    assert faulted.retry_after_s >= 1


def test_patch_bodies_contribute_keys_and_field_hashes(raw_client: TestClient) -> None:
    raw_client.patch("/v1/hunts/hnt_1", json={"name": "Beacon hunt"})
    observer: Observer = raw_client.app.state.observer  # type: ignore[attr-defined]
    record = only(observer)
    assert record.body_keys == ("name",)
    assert record.route == "/v1/hunts/{hunt_id}"
    assert record.body_fields["name"] == record.resource_fields["name"]


def test_get_responses_supply_the_current_field_hashes(raw_client: TestClient) -> None:
    raw_client.get("/v1/hunts/hnt_1")
    observer: Observer = raw_client.app.state.observer  # type: ignore[attr-defined]
    assert set(only(observer).resource_fields) == {"id", "name", "description"}


def test_streaming_responses_are_never_buffered(raw_client: TestClient) -> None:
    response = raw_client.get("/v1/sessions/1/pcap")
    assert len(response.content) == 2048
    observer: Observer = raw_client.app.state.observer  # type: ignore[attr-defined]
    record = only(observer)
    assert record.status == 200
    assert record.resource_fields == {}


def test_an_aborted_request_is_still_recorded(raw_client: TestClient) -> None:
    with pytest.raises(RuntimeError, match="connection died"):
        raw_client.get("/v1/boom")
    observer: Observer = raw_client.app.state.observer  # type: ignore[attr-defined]
    record = only(observer)
    assert record.dropped is True
    assert record.status == 499


def test_stream_lifecycle_events(recorder: Observer) -> None:
    recorder.sse_opened("fam_a", "ana@quillmere.example")
    recorder.sse_closed("fam_a", reason="rotate")
    recorder.sse_opened("fam_a", resume_from=42)
    recorder.ws_opened("fam_a")
    recorder.ws_subscribed("fam_a")
    recorder.ws_pong("fam_a")
    recorder.ws_closed("fam_a", code=4408)
    recorder.ws_rejected("fam_a", "ticket_reuse")
    events = recorder.families()[0].streams
    assert [event.kind for event in events] == [
        "sse_open",
        "sse_close",
        "sse_open",
        "ws_open",
        "ws_subscribe",
        "ws_pong",
        "ws_close",
        "ws_rejected",
    ]
    assert events[2].resume_from == 42
    assert recorder.open_stream_counts() == (1, 0)


def test_the_ring_is_bounded_unless_full_history_is_on() -> None:
    clock = FakeTimeSource()
    small = Observer(clock, ring_size=3)
    full_history = Observer(clock, full_history=True, ring_size=3)
    for observer in (small, full_history):
        for index in range(10):
            observer.record(
                observer.next_record(
                    family_id="fam_a",
                    user="ana@quillmere.example",
                    method="GET",
                    route="/v1/me",
                    path=f"/v1/me/{index}",
                    query="",
                    query_hash="x",
                    status=200,
                    duration_ms=1.0,
                    has_authorization=True,
                )
            )
    assert small.request_count() == 3
    assert full_history.request_count() == 10
    assert full_history.full_history is True


def test_route_template_falls_back_to_a_heuristic() -> None:
    assert route_template({}, "/v1/searches/srch_ab12") == "/v1/searches/{id}"
    assert route_template({}, "/v1/sessions/72075232438042624") == "/v1/sessions/{id}"
    assert route_template({}, "/v1/meta/enums/protocol") == "/v1/meta/enums/protocol"


def test_reset_forgets_everything(recorder: Observer) -> None:
    recorder.sse_opened("fam_a")
    recorder.remember_identity("ip:1|ua", "fam_a", "ana@quillmere.example")
    recorder.reset()
    assert recorder.families() == []
    assert recorder.sticky_identity("ip:1|ua") == (ANONYMOUS, ANONYMOUS)
