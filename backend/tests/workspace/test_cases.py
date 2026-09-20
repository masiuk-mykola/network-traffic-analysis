from fastapi.testclient import TestClient

from tests.conftest import ANALYST, LoggedIn, do_login

ADMIN = {"X-Admin-Token": "lf-dev-admin"}


def open_case(client: TestClient, auth: LoggedIn, title: str = "Branch uploads") -> dict[str, str]:
    response = client.post(
        "/v1/cases", json={"title": title, "severity": "high"}, headers=auth.headers
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_two_cases_are_seeded_newest_first(client: TestClient, analyst: LoggedIn) -> None:
    body = client.get("/v1/cases", headers=analyst.headers).json()

    assert [case["id"] for case in body["items"]] == ["CASE-0002", "CASE-0001"]
    assert body["next_cursor"] is None
    first, second = body["items"]
    assert first["title"] == "Harbor branch anomalies"
    assert first["status"] == "open"
    assert first["owner_id"] == "sam"
    assert first["note_count"] == 1
    assert second["status"] == "closed"


def test_paging_uses_an_opaque_cursor(client: TestClient, analyst: LoggedIn) -> None:
    page = client.get("/v1/cases?limit=1", headers=analyst.headers).json()
    assert [case["id"] for case in page["items"]] == ["CASE-0002"]
    assert page["next_cursor"]

    rest = client.get(
        f"/v1/cases?limit=1&cursor={page['next_cursor']}", headers=analyst.headers
    ).json()
    assert [case["id"] for case in rest["items"]] == ["CASE-0001"]
    assert rest["next_cursor"] is None


def test_a_tampered_cursor_is_400(client: TestClient, analyst: LoggedIn) -> None:
    response = client.get("/v1/cases?cursor=MTIzLmZha2U", headers=analyst.headers)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


def test_create_answers_201_with_an_etag_and_rejects_a_duplicate_title(
    client: TestClient, analyst: LoggedIn
) -> None:
    response = client.post(
        "/v1/cases",
        json={"title": "Branch uploads", "severity": "high", "summary": "Large PUTs at night"},
        headers=analyst.headers,
    )

    assert response.status_code == 201
    case = response.json()
    assert case["id"] == "CASE-0003"
    assert case["status"] == "open"
    assert case["owner_id"] == "ana"
    assert case["version"] == 1
    assert case["evidence"] == []
    assert response.headers["ETag"] == '"v1"'

    clash = client.post(
        "/v1/cases", json={"title": "BRANCH UPLOADS", "severity": "low"}, headers=analyst.headers
    )
    assert clash.status_code == 409
    assert clash.json()["code"] == "title_taken"


def test_get_carries_the_etag_and_unknown_ids_are_404(
    client: TestClient, analyst: LoggedIn
) -> None:
    found = client.get("/v1/cases/CASE-0001", headers=analyst.headers)
    assert found.status_code == 200
    assert found.headers["ETag"] == '"v1"'
    assert found.json()["notes"][0]["author_id"] == "sam"

    missing = client.get("/v1/cases/CASE-9999", headers=analyst.headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "case_not_found"


def test_patch_requires_if_match_and_rejects_a_stale_one(
    client: TestClient, analyst: LoggedIn
) -> None:
    without = client.patch(
        "/v1/cases/CASE-0002", json={"status": "in_progress"}, headers=analyst.headers
    )
    assert without.status_code == 428
    assert without.json()["code"] == "precondition_required"

    stale = client.patch(
        "/v1/cases/CASE-0002",
        json={"status": "in_progress"},
        headers={**analyst.headers, "If-Match": '"v4"'},
    )
    assert stale.status_code == 412
    assert stale.json()["current"]["id"] == "CASE-0002"

    ok = client.patch(
        "/v1/cases/CASE-0002",
        json={"status": "in_progress", "severity": "high"},
        headers={**analyst.headers, "If-Match": '"v1"'},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "in_progress"
    assert ok.json()["severity"] == "high"
    assert ok.headers["ETag"] == '"v2"'


def test_summary_null_removes_it(client: TestClient, analyst: LoggedIn) -> None:
    response = client.patch(
        "/v1/cases/CASE-0002",
        content=b'{"summary": null}',
        headers={
            **analyst.headers,
            "If-Match": '"v1"',
            "Content-Type": "application/merge-patch+json",
        },
    )

    assert response.status_code == 200
    assert "summary" not in response.json()


def test_pinning_evidence_bumps_the_version_and_dedupes(
    client: TestClient, analyst: LoggedIn
) -> None:
    pinned = client.post(
        "/v1/cases/CASE-0002/evidence",
        json={"session_id": "72057598332633090", "stage": "beacon", "note": "First contact"},
        headers=analyst.headers,
    )
    assert pinned.status_code == 201
    case = pinned.json()
    assert case["version"] == 2
    assert case["evidence"][0]["pinned_by"] == "ana"
    assert case["evidence"][0]["stage"] == "beacon"

    again = client.post(
        "/v1/cases/CASE-0002/evidence",
        json={"session_id": "72057598332633090"},
        headers=analyst.headers,
    )
    assert again.status_code == 200
    assert again.json() == {"duplicate": True}
    assert client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()["version"] == 2


def test_unpinning_is_204_and_idempotent(client: TestClient, analyst: LoggedIn) -> None:
    client.post(
        "/v1/cases/CASE-0002/evidence",
        json={"session_id": "72057598332633090"},
        headers=analyst.headers,
    )

    removed = client.delete(
        "/v1/cases/CASE-0002/evidence/72057598332633090", headers=analyst.headers
    )
    assert removed.status_code == 204

    case = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()
    assert case["evidence"] == []
    assert case["version"] == 3

    again = client.delete("/v1/cases/CASE-0002/evidence/72057598332633090", headers=analyst.headers)
    assert again.status_code == 204
    assert client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()["version"] == 3


def test_notes_are_append_only_and_bump_the_version(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post(
        "/v1/cases/CASE-0002/notes",
        json={"body": "Pulled the PCAP of the first beacon."},
        headers=analyst.headers,
    )

    assert response.status_code == 201
    note = response.json()
    assert note["author_id"] == "ana"
    assert note["body"] == "Pulled the PCAP of the first beacon."
    assert response.headers["ETag"] == '"v2"'

    case = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()
    assert [entry["body"] for entry in case["notes"]][-1] == "Pulled the PCAP of the first beacon."
    assert len(case["notes"]) == 2


def test_note_validation_points_into_the_body(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post("/v1/cases/CASE-0002/notes", json={"body": ""}, headers=analyst.headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "body"]


def test_observers_read_cases_but_cannot_change_them(
    client: TestClient, observer: LoggedIn
) -> None:
    assert client.get("/v1/cases", headers=observer.headers).status_code == 200
    assert client.get("/v1/cases/CASE-0001", headers=observer.headers).status_code == 200

    for response in (
        client.post(
            "/v1/cases", json={"title": "Nope", "severity": "low"}, headers=observer.headers
        ),
        client.patch(
            "/v1/cases/CASE-0002",
            json={"status": "closed"},
            headers={**observer.headers, "If-Match": '"v1"'},
        ),
        client.post(
            "/v1/cases/CASE-0002/evidence",
            json={"session_id": "72057598332633090"},
            headers=observer.headers,
        ),
        client.post("/v1/cases/CASE-0002/notes", json={"body": "hi"}, headers=observer.headers),
    ):
        assert response.status_code == 403
        assert response.json()["required"] == "cases:write"


def test_admin_reset_reseeds_the_two_cases(client: TestClient, analyst: LoggedIn) -> None:
    open_case(client, analyst)
    client.post("/v1/cases/CASE-0002/notes", json={"body": "scratch"}, headers=analyst.headers)

    assert client.post("/v1/__admin/reset", headers=ADMIN).status_code == 204

    after = do_login(client, *ANALYST)
    body = client.get("/v1/cases", headers=after.headers).json()
    assert [case["id"] for case in body["items"]] == ["CASE-0002", "CASE-0001"]
    assert body["items"][0]["version"] == 1
