import io
import json
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from capture_api.world.types import Row, World
from tests.conftest import ANALYST, LoggedIn, do_login

ADMIN = {"X-Admin-Token": "lf-dev-admin"}
HOUR_MS = 3_600_000


def world_of(client: TestClient) -> World:
    return client.app.state.world  # type: ignore[attr-defined,no-any-return]


def retained_row(client: TestClient) -> Row:
    world = world_of(client)
    for row in world.rows_desc("hq-core", world.epoch_ms - HOUR_MS, world.epoch_ms):
        if world.pcap_available(row):
            return row
    pytest.fail("no retained session in the last hour")


def row_with_a_file(client: TestClient) -> Row | None:
    world = world_of(client)
    for row in world.rows_desc("hq-core", world.epoch_ms - 24 * HOUR_MS, world.epoch_ms):
        if row.files and not any(spec.purged for spec in row.files):
            return row
    return None


def pin(client: TestClient, auth: LoggedIn, case_id: str, row: Row, stage: str = "beacon") -> None:
    response = client.post(
        f"/v1/cases/{case_id}/evidence",
        json={"session_id": str(row.id), "stage": stage},
        headers=auth.headers,
    )
    assert response.status_code in (200, 201), response.text


def start_export(client: TestClient, auth: LoggedIn, case_id: str = "CASE-0002") -> dict[str, Any]:
    response = client.post(f"/v1/cases/{case_id}/exports", headers=auth.headers)
    assert response.status_code == 202, response.text
    assert response.headers["Location"] == f"/v1/exports/{response.json()['id']}"
    return dict(response.json())


def test_create_answers_202_queued(client: TestClient, analyst: LoggedIn) -> None:
    export = start_export(client, analyst)

    assert export["id"].startswith("exp_")
    assert export["case_id"] == "CASE-0002"
    assert export["state"] == "queued"
    assert export["percent"] == 0
    assert "expires_at" not in export


def test_downloading_before_it_is_ready_is_409(client: TestClient, analyst: LoggedIn) -> None:
    export = start_export(client, analyst)

    response = client.get(f"/v1/exports/{export['id']}/file", headers=analyst.headers)

    assert response.status_code == 409
    assert response.json()["code"] == "not_ready"


def test_an_unknown_export_is_404(client: TestClient, analyst: LoggedIn) -> None:
    response = client.get("/v1/exports/exp_nope", headers=analyst.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "export_not_found"


def test_the_job_becomes_ready_and_the_zip_holds_the_evidence(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    row = retained_row(client)
    pin(client, analyst, "CASE-0002", row)
    export = start_export(client, analyst)

    fake_time.advance(3)
    state = client.get(f"/v1/exports/{export['id']}", headers=analyst.headers).json()
    assert state["state"] == "ready"
    assert state["percent"] == 100
    assert state["expires_at"]

    download = client.get(f"/v1/exports/{export['id']}/file", headers=analyst.headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "content-length" not in download.headers
    assert download.headers["Content-Disposition"].startswith("attachment; filename=")

    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = set(archive.namelist())
        assert {"evidence.json", "report.html"} <= names
        assert f"pcaps/{row.id}.pcap" in names
        document = json.loads(archive.read("evidence.json"))
        report = archive.read("report.html").decode()

    assert document["case"]["id"] == "CASE-0002"
    assert document["evidence"][0]["session_id"] == str(row.id)
    assert document["evidence"][0]["stage"] == "beacon"
    assert document["evidence"][0]["session"]["sensor_id"] == "hq-core"
    assert document["notes"]
    assert "Harbor branch anomalies" in report


def test_the_zip_carries_carved_files(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    row = row_with_a_file(client)
    if row is None:  # pragma: no cover - seed 'test' always has carved files
        pytest.skip("no carved file in the last 24 h of this seed")
    pin(client, analyst, "CASE-0002", row, stage="collection")
    export = start_export(client, analyst)
    fake_time.advance(3)

    download = client.get(f"/v1/exports/{export['id']}/file", headers=analyst.headers)

    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        carved = [name for name in archive.namelist() if name.startswith("files/")]
        assert carved
        assert archive.read(carved[0])


def test_the_filename_survives_a_non_ascii_case_title(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    case = client.post(
        "/v1/cases",
        json={"title": "Hafenbüro Nord — Übersicht", "severity": "medium"},
        headers=analyst.headers,
    ).json()
    export = start_export(client, analyst, case["id"])
    fake_time.advance(3)

    download = client.get(f"/v1/exports/{export['id']}/file", headers=analyst.headers)

    disposition = download.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in disposition
    assert "%C3%BC" in disposition
    ascii_part = disposition.split(";")[1]
    assert all(ord(character) < 128 for character in ascii_part)


def test_an_export_expires_after_fifteen_minutes(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    export = start_export(client, analyst)
    fake_time.advance(3)
    assert client.get(f"/v1/exports/{export['id']}", headers=analyst.headers).json()["state"]

    fake_time.advance(901)
    later = do_login(client, *ANALYST)

    state = client.get(f"/v1/exports/{export['id']}", headers=later.headers)
    assert state.status_code == 404
    assert state.json()["code"] == "export_expired"

    download = client.get(f"/v1/exports/{export['id']}/file", headers=later.headers)
    assert download.status_code == 404
    assert download.json()["code"] == "export_expired"


def test_degraded_pcap_blocks_the_download(
    client: TestClient, analyst: LoggedIn, fake_time: Any
) -> None:
    export = start_export(client, analyst)
    fake_time.advance(3)
    assert (
        client.put(
            "/v1/__admin/chaos", json={"profile": "degraded-pcap"}, headers=ADMIN
        ).status_code
        == 200
    )

    response = client.get(f"/v1/exports/{export['id']}/file", headers=analyst.headers)

    assert response.status_code == 503
    assert response.json()["code"] == "pcap_store_degraded"
    assert response.headers["Retry-After"] == "30"


def test_the_same_idempotency_key_replays_the_job(client: TestClient, analyst: LoggedIn) -> None:
    headers = {**analyst.headers, "Idempotency-Key": "export-key-0001"}

    first = client.post("/v1/cases/CASE-0002/exports", headers=headers)
    second = client.post("/v1/cases/CASE-0002/exports", headers=headers)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]


def test_the_same_key_for_another_case_is_422(client: TestClient, analyst: LoggedIn) -> None:
    headers = {**analyst.headers, "Idempotency-Key": "export-key-0002"}
    client.post("/v1/cases/CASE-0002/exports", headers=headers)

    response = client.post("/v1/cases/CASE-0001/exports", headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_mismatch"


def test_a_malformed_idempotency_key_is_422(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post(
        "/v1/cases/CASE-0002/exports", headers={**analyst.headers, "Idempotency-Key": "short"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_idempotency_key"


def test_exporting_an_unknown_case_is_404(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post("/v1/cases/CASE-9999/exports", headers=analyst.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "case_not_found"


def test_observers_cannot_export(client: TestClient, observer: LoggedIn) -> None:
    response = client.post("/v1/cases/CASE-0002/exports", headers=observer.headers)

    assert response.status_code == 403
    assert response.json()["required"] == "cases:write"
