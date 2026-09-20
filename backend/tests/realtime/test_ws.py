from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from capture_api.domain.models import SearchProgress
from capture_api.world.clock import FakeTimeSource
from tests.conftest import ANALYST, do_login
from tests.realtime.conftest import (
    BRANCH,
    HQ,
    Built,
    ClientFactory,
    Script,
    session_row,
)

ADMIN = {"X-Admin-Token": "lf-dev-admin"}
ALLOWED_ORIGIN = "http://localhost:3000"


def ticket_for(client: TestClient, *sensors: str, account: tuple[str, str] = ANALYST) -> str:
    logged = do_login(client, *account)
    response = client.post(
        "/v1/live/tickets", json={"sensor_ids": list(sensors)}, headers=logged.headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["ticket"])


def connect(client: TestClient, ticket: str, *, origin: str | None = None) -> WebSocketTestSession:
    headers = {"Origin": origin} if origin else {}
    return client.websocket_connect(f"/v1/live?ticket={ticket}", headers=headers)


def close_code(
    connection: AbstractContextManager[WebSocketTestSession],
    drive: Callable[[WebSocketTestSession], None],
) -> int:
    try:
        with connection as socket:
            drive(socket)
    except WebSocketDisconnect as disconnect:
        return disconnect.code
    raise AssertionError("the socket stayed open")


def subscribe(
    socket: WebSocketTestSession,
    *sensors: str,
    channels: tuple[str, ...] = ("sessions", "stats"),
    sub_id: str = "s1",
) -> dict[str, Any]:
    socket.send_json(
        {
            "type": "subscribe",
            "sub_id": sub_id,
            "sensor_ids": list(sensors),
            "filter": None,
            "channels": list(channels),
        }
    )
    return dict(socket.receive_json())


def read_until(socket: WebSocketTestSession, kind: str, limit: int = 700) -> dict[str, Any]:
    for _ in range(limit):
        frame = dict(socket.receive_json())
        if frame["type"] == kind:
            return frame
    raise AssertionError(f"no {kind} frame in {limit} frames")


def test_the_socket_greets_and_acknowledges(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        hello = socket.receive_json()
        ack = subscribe(socket, HQ)

    assert hello["type"] == "hello"
    assert hello["heartbeat_s"] == 15
    assert hello["server_time"].endswith("Z")
    assert ack == {"type": "ack", "sub_id": "s1", "generation": 1}


def test_live_sessions_and_stats_follow_the_capture_clock(
    realtime: Built, fake_time: FakeTimeSource
) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        subscribe(socket, HQ)
        fake_time.advance(10)
        first = socket.receive_json()
        stats = read_until(socket, "stats")

    assert first["type"] == "session"
    assert first["generation"] == 1
    assert first["seq"] == 1
    assert first["row"]["sensor_id"] == HQ
    assert first["row"]["summary"] == "scripted row 0"
    assert "synthetic" not in first
    assert stats["by_protocol"]["dns"]["sessions"] == 6


def test_a_new_subscription_bumps_the_generation(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ, BRANCH)

    with connect(client, ticket) as socket:
        socket.receive_json()
        first = subscribe(socket, HQ)
        second = subscribe(socket, BRANCH, sub_id="s2")

    assert first["generation"] == 1
    assert second == {"type": "ack", "sub_id": "s2", "generation": 2}


def test_pausing_stops_the_session_frames(realtime: Built, fake_time: FakeTimeSource) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        subscribe(socket, HQ, channels=("sessions", "stats"))
        socket.send_json({"type": "pause"})
        fake_time.advance(10)
        stats = read_until(socket, "stats")
        socket.send_json({"type": "resume"})
        fake_time.advance(1)
        resumed = read_until(socket, "session")

    assert stats["by_protocol"] == {}
    assert resumed["row"]["sensor_id"] == HQ


def test_a_sensor_outside_the_ticket_closes_the_socket(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    def drive(socket: WebSocketTestSession) -> None:
        socket.receive_json()
        subscribe(socket, BRANCH)

    assert close_code(connect(client, ticket), drive) == 4403


def test_a_malformed_frame_is_answered_but_keeps_the_socket(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        socket.send_json({"type": "nonsense"})
        error = socket.receive_json()
        ack = subscribe(socket, HQ)

    assert error == {"type": "error", "code": "bad_frame", "message": error["message"]}
    assert ack["type"] == "ack"


def test_a_ping_is_answered_and_the_next_one_follows(
    realtime: Built, fake_time: FakeTimeSource
) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        fake_time.advance(15)
        ping = socket.receive_json()
        socket.send_json({"type": "pong", "nonce": ping["nonce"]})
        fake_time.advance(15)
        second = socket.receive_json()

    assert ping["type"] == "ping"
    assert second["type"] == "ping"
    assert second["nonce"] != ping["nonce"]


def test_a_missed_pong_closes_the_socket(realtime: Built, fake_time: FakeTimeSource) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    def drive(socket: WebSocketTestSession) -> None:
        socket.receive_json()
        fake_time.advance(15)
        assert socket.receive_json()["type"] == "ping"
        fake_time.advance(11)
        socket.receive_json()

    assert close_code(connect(client, ticket), drive) == 4408


def test_an_unknown_origin_is_refused(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    connection = connect(client, ticket, origin="https://phish.example")

    assert close_code(connection, lambda socket: socket.receive_json()) == 4403


def test_the_console_origin_is_accepted(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket, origin=ALLOWED_ORIGIN) as socket:
        hello = socket.receive_json()

    assert hello["type"] == "hello"


def test_a_reused_ticket_is_refused(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()

    assert close_code(connect(client, ticket), lambda socket: socket.receive_json()) == 4401


def test_an_expired_ticket_is_refused(realtime: Built, fake_time: FakeTimeSource) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)
    fake_time.advance(31)

    assert close_code(connect(client, ticket), lambda socket: socket.receive_json()) == 4401


def test_revoking_the_family_closes_the_socket(realtime: Built) -> None:
    client = realtime.client
    logged = do_login(client, *ANALYST)
    ticket = str(
        client.post("/v1/live/tickets", json={"sensor_ids": [HQ]}, headers=logged.headers).json()[
            "ticket"
        ]
    )

    def drive(socket: WebSocketTestSession) -> None:
        socket.receive_json()
        assert client.post("/v1/auth/logout", headers=logged.headers).status_code == 204
        socket.receive_json()

    assert close_code(connect(client, ticket), drive) == 1000


def test_the_storm_profile_restarts_the_socket(
    make_realtime: ClientFactory, fake_time: FakeTimeSource
) -> None:
    built = make_realtime(chaos="storm")
    ticket = ticket_for(built.client, HQ)

    def drive(socket: WebSocketTestSession) -> None:
        socket.receive_json()
        fake_time.advance(91)
        for _ in range(4):
            socket.receive_json()

    assert close_code(connect(built.client, ticket), drive) == 1013


def test_a_burst_drops_frames_and_reports_lagging(
    make_realtime: ClientFactory, fake_time: FakeTimeSource, epoch_ms: int
) -> None:
    script = Script((), (session_row(0, epoch_ms + 1_000),))
    built = make_realtime(world_script=script)
    assert (
        built.client.put(
            "/v1/__admin/chaos",
            json={"profile": "calm", "overrides": {"live_burst": 520}},
            headers=ADMIN,
        ).status_code
        == 200
    )
    ticket = ticket_for(built.client, HQ)

    with connect(built.client, ticket) as socket:
        socket.receive_json()
        subscribe(socket, HQ, channels=("sessions",))
        fake_time.advance(10)
        first = socket.receive_json()
        synthetic = socket.receive_json()
        lagging = read_until(socket, "lagging")

    assert first["type"] == "session"
    assert "synthetic" not in first
    assert synthetic["synthetic"] is True
    assert lagging["dropped"] == 21
    assert 0 < lagging["sample_rate"] < 1


@dataclass(slots=True)
class StubJob:
    state: str = "running"
    progress: SearchProgress = field(
        default_factory=lambda: SearchProgress(
            scanned_sessions=10,
            total_sessions_estimate=100,
            matched=2,
            matched_is_estimate=True,
            percent=10.0,
        )
    )


@dataclass(slots=True)
class StubSearches:
    jobs: dict[str, StubJob] = field(default_factory=dict)

    def peek(self, search_id: str) -> StubJob | None:
        return self.jobs.get(search_id)


@pytest.fixture
def searches(realtime: Built) -> Iterator[StubSearches]:
    stub = StubSearches({"srch_1": StubJob()})
    previous = getattr(realtime.app.state, "searches", None)
    realtime.app.state.searches = stub
    yield stub
    realtime.app.state.searches = previous


def test_a_watched_search_reports_its_progress(
    realtime: Built, searches: StubSearches, fake_time: FakeTimeSource
) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        socket.send_json({"type": "watch_search", "search_id": "srch_1"})
        first = socket.receive_json()
        searches.jobs["srch_1"] = StubJob(
            state="done",
            progress=SearchProgress(
                scanned_sessions=100,
                total_sessions_estimate=100,
                matched=7,
                matched_is_estimate=False,
                percent=100.0,
            ),
        )
        fake_time.advance(1)
        second = read_until(socket, "search_progress")

    assert first["type"] == "search_progress"
    assert first["search_id"] == "srch_1"
    assert first["progress"]["percent"] == 10.0
    assert second["state"] == "done"
    assert second["progress"]["matched"] == 7


def test_watching_an_unknown_search_is_an_error_frame(
    realtime: Built, searches: StubSearches
) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        socket.send_json({"type": "watch_search", "search_id": "srch_gone"})
        error = socket.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "search_not_found"


def test_the_observer_records_the_socket_lifecycle(
    realtime: Built, fake_time: FakeTimeSource
) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
        subscribe(socket, HQ)
        fake_time.advance(15)
        ping = read_until(socket, "ping")
        socket.send_json({"type": "pong", "nonce": ping["nonce"]})
        fake_time.advance(1)
        read_until(socket, "stats")

    observer = realtime.app.state.observer
    kinds = [event.kind for family in observer.families() for event in family.streams]
    assert "ws_open" in kinds
    assert "ws_subscribe" in kinds
    assert "ws_pong" in kinds


def test_a_refused_handshake_is_attributed_to_its_family(realtime: Built) -> None:
    client = realtime.client
    ticket = ticket_for(client, HQ)

    with connect(client, ticket) as socket:
        socket.receive_json()
    assert close_code(connect(client, ticket), lambda socket: socket.receive_json()) == 4401

    observer = realtime.app.state.observer
    rejected = [
        event
        for family in observer.families()
        for event in family.streams
        if event.kind == "ws_rejected"
    ]
    assert [(event.reason, event.code) for event in rejected] == [("ticket_reuse", 4401)]
    assert rejected[0].family_id.startswith("fam_")
