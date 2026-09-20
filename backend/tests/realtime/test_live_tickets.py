from fastapi.testclient import TestClient

from capture_api.world.clock import FakeTimeSource
from tests.conftest import ANALYST, OBSERVER, do_login
from tests.realtime.conftest import BRANCH, DENIED, HQ, Built

TICKETS = "/v1/live/tickets"


def test_a_ticket_is_minted_for_the_requested_sensors(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    response = client.post(TICKETS, json={"sensor_ids": [HQ, BRANCH]}, headers=logged.headers)

    assert response.status_code == 201
    body = response.json()
    assert body["ticket"].startswith("lt_")
    assert body["expires_in"] == 30
    assert body["ws_url"] == "ws://testserver/v1/live"


def test_an_observer_may_open_the_live_tap(client: TestClient) -> None:
    logged = do_login(client, *OBSERVER)

    response = client.post(TICKETS, json={"sensor_ids": [HQ]}, headers=logged.headers)

    assert response.status_code == 201


def test_an_unreadable_sensor_is_refused(client: TestClient) -> None:
    logged = do_login(client, *OBSERVER)

    response = client.post(TICKETS, json={"sensor_ids": [DENIED]}, headers=logged.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_sensor"


def test_an_unknown_sensor_is_a_422(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    response = client.post(TICKETS, json={"sensor_ids": ["imp-9"]}, headers=logged.headers)

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_sensor"
    assert response.json()["loc"] == ["body", "sensor_ids", 0]


def test_at_most_three_sensors(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    response = client.post(
        TICKETS, json={"sensor_ids": [HQ, BRANCH, DENIED, "imp-1"]}, headers=logged.headers
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_a_ticket_needs_an_account(client: TestClient) -> None:
    assert client.post(TICKETS, json={"sensor_ids": [HQ]}).status_code == 401


def test_a_ticket_survives_exactly_one_handshake(realtime: Built) -> None:
    client = realtime.client
    logged = do_login(client, *ANALYST)
    ticket = client.post(TICKETS, json={"sensor_ids": [HQ]}, headers=logged.headers).json()[
        "ticket"
    ]
    live = realtime.app.state.live

    assert live.redeem(ticket)[1] == "ok"
    assert live.redeem(ticket)[1] == "ticket_reuse"


def test_a_ticket_expires_after_thirty_seconds(realtime: Built, fake_time: FakeTimeSource) -> None:
    client = realtime.client
    logged = do_login(client, *ANALYST)
    ticket = client.post(TICKETS, json={"sensor_ids": [HQ]}, headers=logged.headers).json()[
        "ticket"
    ]

    fake_time.advance(31)

    assert realtime.app.state.live.redeem(ticket)[1] == "ticket_expired"


def test_an_unknown_ticket_is_refused(realtime: Built) -> None:
    assert realtime.app.state.live.redeem("lt_nope")[1] == "ticket_invalid"
    assert realtime.app.state.live.redeem(None)[1] == "ticket_missing"
