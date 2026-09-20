import hashlib
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from capture_api.workspace.imports import READ_RATE_BPS, CaptureScanner, ImportStore
from capture_api.world.types import World
from tests.conftest import ANALYST, LoggedIn, do_login
from tests.workspace.conftest import EPOCH_MS, sample_capture, upload

PCAPNG = b"\x0a\x0d\x0d\x0a" + b"\x00" * 60
NOT_A_CAPTURE = b"PK\x03\x04" + b"\x00" * 200


def world_of(client: TestClient) -> World:
    return client.app.state.world  # type: ignore[attr-defined,no-any-return]


def store_of(client: TestClient) -> ImportStore:
    return client.app.state.imports  # type: ignore[attr-defined,no-any-return]


def test_the_scanner_reads_the_capture_time_range() -> None:
    data = sample_capture()
    scanner = CaptureScanner()

    for start in range(0, len(data), 7):
        scanner.feed(data[start : start + 7])

    assert scanner.kind == "pcap"
    assert scanner.size == len(data)
    assert scanner.hexdigest() == hashlib.sha256(data).hexdigest()
    assert scanner.first_ts_ms == EPOCH_MS - 3_600_000
    assert scanner.last_ts_ms is not None
    assert scanner.last_ts_ms >= scanner.first_ts_ms


def test_the_scanner_recognises_pcapng_without_walking_it() -> None:
    scanner = CaptureScanner()
    scanner.feed(PCAPNG)

    assert scanner.kind == "pcapng"
    assert scanner.first_ts_ms is None


def test_the_scanner_rejects_a_foreign_magic() -> None:
    scanner = CaptureScanner()
    scanner.feed(NOT_A_CAPTURE)

    assert scanner.magic_decided is True
    assert scanner.is_capture is False


def test_a_pcapng_is_placed_in_the_hour_before_the_epoch(client: TestClient) -> None:
    store = store_of(client)

    record = store.create(
        label="Ad-hoc capture",
        tz="Europe/Lisbon",
        sha256="a" * 64,
        size=8192,
        first_ts_ms=None,
        last_ts_ms=None,
    )

    assert (record.first_ts_ms, record.last_ts_ms) == store.default_window()
    assert record.last_ts_ms - record.first_ts_ms == 3_600_000


def test_the_documented_read_rate_is_eight_megabytes_per_second() -> None:
    assert READ_RATE_BPS == 8 * 1024 * 1024


def test_observers_cannot_import(client: TestClient, observer: LoggedIn) -> None:
    response = client.post("/v1/imports", headers=observer.headers, **upload(sample_capture()))

    assert response.status_code == 403
    assert response.json()["required"] == "imports:create"


def test_a_declared_length_over_the_limit_is_413(
    client: TestClient, analyst: LoggedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("capture_api.workspace.imports.MAX_UPLOAD_BYTES", 64)

    response = client.post("/v1/imports", headers=analyst.headers, **upload(sample_capture()))

    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert response.json()["limit_bytes"] == 64


def test_a_foreign_magic_is_415(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post("/v1/imports", headers=analyst.headers, **upload(NOT_A_CAPTURE))

    assert response.status_code == 415
    assert response.json()["code"] == "not_a_capture"


def test_a_truncated_upload_fails_the_checksum(client: TestClient, analyst: LoggedIn) -> None:
    data = sample_capture()
    whole = hashlib.sha256(data).hexdigest()

    response = client.post(
        "/v1/imports", headers=analyst.headers, **upload(data[: len(data) // 2], sha256=whole)
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "checksum_mismatch"
    assert body["expected"] == whole
    assert body["actual"] != whole


def test_a_truncated_upload_with_its_own_digest_is_accepted(
    client: TestClient, analyst: LoggedIn
) -> None:
    data = sample_capture()

    response = client.post("/v1/imports", headers=analyst.headers, **upload(data[: len(data) // 2]))

    assert response.status_code == 202


def test_a_missing_meta_part_is_422(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post(
        "/v1/imports",
        headers=analyst.headers,
        files={"file": ("capture.pcap", sample_capture(), "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "meta"]


def test_a_bad_time_zone_points_into_meta(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post(
        "/v1/imports", headers=analyst.headers, **upload(sample_capture(), tz="Mars/Olympus")
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "meta", "tz"]


def test_a_body_that_is_not_multipart_is_422(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post("/v1/imports", headers=analyst.headers, json={"file": "nope"})

    assert response.status_code == 422
    assert response.json()["code"] == "bad_multipart"


def test_the_body_is_read_at_the_configured_rate(
    client: TestClient, analyst: LoggedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("capture_api.workspace.imports.READ_RATE_BPS", 4096)
    data = sample_capture()

    started = time.monotonic()
    response = client.post("/v1/imports", headers=analyst.headers, **upload(data))
    elapsed = time.monotonic() - started

    assert response.status_code == 202
    assert elapsed >= len(data) / 4096 * 0.5


def test_a_capture_is_accepted_indexed_and_becomes_a_sensor(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    data = sample_capture()
    digest = hashlib.sha256(data).hexdigest()

    accepted = client.post(
        "/v1/imports", headers=analyst.headers, **upload(data, label="Branch tap 2025-10")
    )
    assert accepted.status_code == 202
    created = accepted.json()
    assert created["id"].startswith("imp_")
    assert created["state"] == "received"
    assert created["progress"] == 0
    assert created["sha256"] == digest
    assert created["label"] == "Branch tap 2025-10"
    assert created["sensor_id"] == "imp-1"
    assert accepted.headers["Location"] == f"/v1/imports/{created['id']}"

    fake_time.advance(3)
    halfway = client.get(f"/v1/imports/{created['id']}", headers=analyst.headers).json()
    assert halfway["state"] == "indexing"
    assert 0 < halfway["progress"] < 100

    fake_time.advance(8)
    ready = client.get(f"/v1/imports/{created['id']}", headers=analyst.headers).json()
    assert ready["state"] == "ready"
    assert ready["progress"] == 100
    assert ready["sessions_indexed"] > 0
    assert ready["sensor_id"] == "imp-1"

    sensors = {sensor.id: sensor for sensor in world_of(client).sensors()}
    assert "imp-1" in sensors
    imported = sensors["imp-1"]
    assert imported.kind == "import"
    assert imported.name == "Branch tap 2025-10"
    assert imported.decoder_version == "v2"
    assert imported.status == "online"


def test_the_sessions_land_inside_the_captures_own_time_range(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    start_ms = EPOCH_MS - 7_200_000
    created = client.post(
        "/v1/imports", headers=analyst.headers, **upload(sample_capture(start_ms))
    ).json()
    fake_time.advance(11)
    client.get(f"/v1/imports/{created['id']}", headers=analyst.headers)

    world = world_of(client)
    rows = list(world.rows("imp-1", world.data_start_ms, world.capture_now_ms()))

    assert rows
    assert all(start_ms <= row.start_ms <= start_ms + 60_000 for row in rows)


def test_the_same_capture_twice_is_a_duplicate(client: TestClient, analyst: LoggedIn) -> None:
    data = sample_capture()
    first = client.post("/v1/imports", headers=analyst.headers, **upload(data)).json()

    again = client.post("/v1/imports", headers=analyst.headers, **upload(data, label="Another"))

    assert again.status_code == 200
    assert again.json() == {"duplicate": True, "id": first["id"], "sensor_id": first["sensor_id"]}


def test_the_same_idempotency_key_replays_the_import(client: TestClient, analyst: LoggedIn) -> None:
    data = sample_capture()
    headers = {**analyst.headers, "Idempotency-Key": "import-key-0001"}

    first = client.post("/v1/imports", headers=headers, **upload(data))
    second = client.post("/v1/imports", headers=headers, **upload(data))

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]


def test_an_unknown_import_is_404(client: TestClient, analyst: LoggedIn) -> None:
    response = client.get("/v1/imports/imp_nope", headers=analyst.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "import_not_found"


def test_admin_reset_forgets_imports_and_their_sensors(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    created = client.post("/v1/imports", headers=analyst.headers, **upload(sample_capture())).json()
    fake_time.advance(11)
    client.get(f"/v1/imports/{created['id']}", headers=analyst.headers)
    assert any(sensor.id == "imp-1" for sensor in world_of(client).sensors())

    reset = client.post("/v1/__admin/reset", headers={"X-Admin-Token": "lf-dev-admin"})
    assert reset.status_code == 204

    after = do_login(client, *ANALYST)
    assert not any(sensor.kind == "import" for sensor in world_of(client).sensors())
    assert client.get(f"/v1/imports/{created['id']}", headers=after.headers).status_code == 404
