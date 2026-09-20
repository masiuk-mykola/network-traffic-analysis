from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.world.world import SimWorld
from tests.conftest import OBSERVER, LoggedIn

from .conftest import Catalog, world_ahead


def test_returns_the_row_and_the_decoded_transaction(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.plain_file.row

    response = client.get(f"/v1/sessions/{row.id}", headers=login().headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(row.id)
    assert body["sensor_id"] == row.sensor_id
    assert body["protocol"] == row.protocol
    assert body["decoder"] == f"{row.protocol}/2"
    assert list(body["decoded"]) == [row.protocol]
    assert body["files_count"] == len(row.files)
    assert len(body["files"]) == len(row.files)
    assert body["pcap"]["available"] is True
    assert isinstance(body["detections"], list)


def test_the_carved_files_carry_their_identity(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    carved = rows.plain_file

    body = client.get(f"/v1/sessions/{carved.session_id}", headers=login().headers).json()

    file = body["files"][carved.ordinal]
    assert file["id"] == carved.file_id
    assert file["name"] == carved.spec.name
    assert file["mime"] == carved.spec.mime
    assert file["size"] == carved.spec.size
    assert len(file["sha256"]) == 64
    assert file["source"] in {"smtp_attachment", "http_body"}
    assert file["purged"] is False


def test_a_detected_session_lists_its_rules(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    row = rows.detected
    raised = row.attr("detection.rule")

    body = client.get(f"/v1/sessions/{row.id}", headers=login().headers).json()

    assert body["detections"]
    assert isinstance(raised, tuple)
    for detection in body["detections"]:
        assert detection["rule_id"] in raised
        assert detection["severity"] in {"low", "medium", "high"}
        assert detection["mitre"]["technique_id"].startswith("T")
        assert detection["rule"]


def test_the_id_stays_a_string_larger_than_2_to_the_53(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    body = client.get(f"/v1/sessions/{rows.plain_file.row.id}", headers=login().headers).json()

    assert isinstance(body["id"], str)
    assert int(body["id"]) > 2**53


def test_the_harbor_branch_answers_the_legacy_v1_shape(
    client: TestClient, login: Callable[..., LoggedIn], world: SimWorld
) -> None:
    row = next(
        candidate
        for candidate in world.rows("harbor-branch", world.epoch_ms - 3_600_000, world.epoch_ms)
        if candidate.protocol == "dns" and candidate.attr("dns.answer")
    )

    body = client.get(f"/v1/sessions/{row.id}", headers=login().headers).json()

    assert body["decoder"] == "dns/1"
    dns = body["decoded"]["dns"]
    assert isinstance(dns["transaction_id"], str), "v1 turns numbers into strings"
    assert isinstance(dns["rcode"], str), "v1 collapses rcode to its numeric string"


def test_an_observer_gets_redacted_smtp_recipients(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    session_id = rows.smtp_with_recipients.id

    analyst = client.get(f"/v1/sessions/{session_id}", headers=login().headers).json()
    observer = client.get(f"/v1/sessions/{session_id}", headers=login(*OBSERVER).headers).json()

    assert all(isinstance(entry, str) for entry in analyst["decoded"]["smtp"]["rcpt_to"])
    assert observer["decoded"]["smtp"]["rcpt_to"] == [
        {"redacted": True} for _ in analyst["decoded"]["smtp"]["rcpt_to"]
    ]


def test_an_observer_cannot_read_the_data_centre_sensor(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    response = client.get(f"/v1/sessions/{rows.dc_east.id}", headers=login(*OBSERVER).headers)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have access to sensor 'dc-east'.",
        "code": "forbidden_sensor",
        "sensor_id": "dc-east",
    }


def test_a_malformed_id_is_a_404_not_a_422(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    headers = login().headers

    for session_id in ("abc", "0123", "42", "-1", "9" * 25, "72057635700998144x"):
        response = client.get(f"/v1/sessions/{session_id}", headers=headers)
        assert response.status_code == 404, session_id
        assert response.json()["code"] == "session_not_found"


def test_a_row_still_inside_the_sensor_lag_is_not_visible_yet(
    client: TestClient, login: Callable[..., LoggedIn], world: SimWorld
) -> None:
    ahead = world_ahead(600)
    lagging = next(
        candidate
        for candidate in ahead.rows("harbor-branch", world.epoch_ms - 200_000, world.epoch_ms)
        if candidate.start_ms > ahead.epoch_ms - 300_000
    )

    response = client.get(f"/v1/sessions/{lagging.id}", headers=login().headers)

    assert world.row(lagging.id) is None, "the harbor branch hides its newest 300 s"
    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_an_unknown_but_well_formed_id_is_a_404(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    response = client.get("/v1/sessions/288230376151711744", headers=login().headers)

    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"


def test_needs_a_token(client: TestClient, rows: Catalog) -> None:
    response = client.get(f"/v1/sessions/{rows.plain_file.row.id}")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
