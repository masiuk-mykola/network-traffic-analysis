import re
from collections.abc import Callable
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.world.world import SimWorld
from tests.conftest import OBSERVER, LoggedIn

LOCAL_TIMESTAMP = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}$")


def test_lists_the_three_built_in_sensors(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    response = client.get("/v1/sensors", headers=login().headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [sensor["id"] for sensor in items] == ["hq-core", "dc-east", "harbor-branch"]


def test_the_harbor_branch_is_a_lagging_v1_sensor(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    items = client.get("/v1/sensors", headers=login().headers).json()["items"]
    harbor = next(sensor for sensor in items if sensor["id"] == "harbor-branch")

    assert harbor["decoder_version"] == "v1"
    assert harbor["status"] == "lagging"
    assert harbor["lag_seconds"] == 300
    assert harbor["tz"] == "Europe/Berlin"
    assert harbor["retention"] == {"metadata_days": 30, "pcap_hours": 48, "files_days": 7}
    assert LOCAL_TIMESTAMP.match(harbor["last_packet_local"])
    assert harbor["last_packet_at"].endswith("Z")


def test_an_observer_sees_the_sensor_it_may_not_read(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    session = login(*OBSERVER)

    listed = client.get("/v1/sensors", headers=session.headers).json()["items"]
    profile = client.get("/v1/me", headers=session.headers).json()

    assert "dc-east" in [sensor["id"] for sensor in listed]
    assert "dc-east" not in profile["sensor_ids"]


def test_a_ready_import_becomes_a_sensor(
    app: FastAPI, client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    world = cast(SimWorld, app.state.world)
    sensor = world.register_import(
        import_id="imp_test",
        label="Hafen forensics dump",
        tz="Europe/Berlin",
        sha256="ab" * 32,
        size=4_000_000,
        first_ts_ms=world.epoch_ms - 3_600_000,
        last_ts_ms=world.epoch_ms - 1_800_000,
    )

    items = client.get("/v1/sensors", headers=login().headers).json()["items"]

    imported = next(entry for entry in items if entry["id"] == sensor.id)
    assert imported["kind"] == "import"
    assert imported["name"] == "Hafen forensics dump"
    assert imported["decoder_version"] == "v2"
    assert imported["lag_seconds"] == 0


def test_needs_a_token(client: TestClient) -> None:
    response = client.get("/v1/sensors")

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
