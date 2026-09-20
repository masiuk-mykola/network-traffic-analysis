from fastapi.testclient import TestClient

from tests.conftest import ANALYST, LoggedIn, do_login
from tests.workspace.conftest import hunt_body, hunt_query

ADMIN = {"X-Admin-Token": "lf-dev-admin"}
MERGE_PATCH = "application/merge-patch+json"


def create(client: TestClient, auth: LoggedIn, name: str = "Branch beacons") -> dict[str, object]:
    response = client.post("/v1/hunts", json=hunt_body(name), headers=auth.headers)
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_create_answers_201_with_location_and_first_etag(
    client: TestClient, analyst: LoggedIn
) -> None:
    response = client.post("/v1/hunts", json=hunt_body(), headers=analyst.headers)

    assert response.status_code == 201
    hunt = response.json()
    assert hunt["id"].startswith("hnt_")
    assert hunt["version"] == 1
    assert hunt["owner_id"] == "ana"
    assert response.headers["ETag"] == '"v1"'
    assert response.headers["Location"] == f"/v1/hunts/{hunt['id']}"
    assert "description" not in hunt


def test_list_is_newest_first_and_private(
    client: TestClient, analyst: LoggedIn, teammate: LoggedIn
) -> None:
    first = create(client, analyst, "Older")
    second = create(client, analyst, "Newer")
    create(client, teammate, "Sam's own")

    mine = client.get("/v1/hunts", headers=analyst.headers).json()["items"]
    assert [hunt["id"] for hunt in mine] == [second["id"], first["id"]]

    theirs = client.get("/v1/hunts", headers=teammate.headers).json()["items"]
    assert [hunt["name"] for hunt in theirs] == ["Sam's own"]


def test_get_returns_the_etag_and_404s_for_another_users_hunt(
    client: TestClient, analyst: LoggedIn, teammate: LoggedIn
) -> None:
    hunt = create(client, analyst)

    mine = client.get(f"/v1/hunts/{hunt['id']}", headers=analyst.headers)
    assert mine.status_code == 200
    assert mine.headers["ETag"] == '"v1"'

    theirs = client.get(f"/v1/hunts/{hunt['id']}", headers=teammate.headers)
    assert theirs.status_code == 404
    assert theirs.json()["code"] == "hunt_not_found"


def test_patch_without_if_match_is_428(client: TestClient, analyst: LoggedIn) -> None:
    hunt = create(client, analyst)

    response = client.patch(
        f"/v1/hunts/{hunt['id']}", json={"name": "Renamed"}, headers=analyst.headers
    )

    assert response.status_code == 428
    assert response.json()["code"] == "precondition_required"


def test_patch_with_a_stale_etag_is_412_carrying_the_current_hunt(
    client: TestClient, analyst: LoggedIn
) -> None:
    hunt = create(client, analyst)
    client.patch(
        f"/v1/hunts/{hunt['id']}",
        json={"name": "First rename"},
        headers={**analyst.headers, "If-Match": '"v1"'},
    )

    stale = client.patch(
        f"/v1/hunts/{hunt['id']}",
        json={"name": "Second rename"},
        headers={**analyst.headers, "If-Match": '"v1"'},
    )

    assert stale.status_code == 412
    body = stale.json()
    assert body["code"] == "etag_mismatch"
    assert body["current"]["version"] == 2
    assert body["current"]["name"] == "First rename"
    assert stale.headers["ETag"] == '"v2"'


def test_merge_patch_content_type_is_accepted_and_bumps_the_version(
    client: TestClient, analyst: LoggedIn
) -> None:
    hunt = create(client, analyst)

    response = client.patch(
        f"/v1/hunts/{hunt['id']}",
        content=b'{"name": "Renamed"}',
        headers={**analyst.headers, "If-Match": '"v1"', "Content-Type": MERGE_PATCH},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["version"] == 2
    assert response.headers["ETag"] == '"v2"'


def test_merge_patch_leaves_untouched_keys_alone(client: TestClient, analyst: LoggedIn) -> None:
    created = client.post(
        "/v1/hunts",
        json=hunt_body("With a description", description="Why this hunt exists"),
        headers=analyst.headers,
    ).json()

    patched = client.patch(
        f"/v1/hunts/{created['id']}",
        json={"query": hunt_query(sort="bytes")},
        headers={**analyst.headers, "If-Match": '"v1"'},
    ).json()

    assert patched["description"] == "Why this hunt exists"
    assert patched["name"] == "With a description"
    assert patched["query"]["sort"] == "bytes"


def test_description_null_removes_it(client: TestClient, analyst: LoggedIn) -> None:
    created = client.post(
        "/v1/hunts",
        json=hunt_body("Has one", description="Remove me"),
        headers=analyst.headers,
    ).json()

    patched = client.patch(
        f"/v1/hunts/{created['id']}",
        json={"description": None},
        headers={**analyst.headers, "If-Match": '"v1"', "Content-Type": MERGE_PATCH},
    )

    assert patched.status_code == 200
    assert "description" not in patched.json()


def test_name_is_unique_per_owner_case_insensitively(
    client: TestClient, analyst: LoggedIn, teammate: LoggedIn
) -> None:
    create(client, analyst, "Branch beacons")

    clash = client.post("/v1/hunts", json=hunt_body("BRANCH BEACONS"), headers=analyst.headers)
    assert clash.status_code == 409
    assert clash.json()["code"] == "name_taken"

    other_owner = client.post(
        "/v1/hunts", json=hunt_body("branch beacons"), headers=teammate.headers
    )
    assert other_owner.status_code == 201


def test_renaming_onto_another_hunts_name_is_409(client: TestClient, analyst: LoggedIn) -> None:
    create(client, analyst, "Taken")
    other = create(client, analyst, "Free")

    response = client.patch(
        f"/v1/hunts/{other['id']}",
        json={"name": "taken"},
        headers={**analyst.headers, "If-Match": '"v1"'},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "name_taken"


def test_validation_errors_point_into_the_body(client: TestClient, analyst: LoggedIn) -> None:
    response = client.post("/v1/hunts", json=hunt_body("x" * 81), headers=analyst.headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "name"]


def test_observers_may_list_but_not_write(client: TestClient, observer: LoggedIn) -> None:
    assert client.get("/v1/hunts", headers=observer.headers).json() == {"items": []}

    forbidden = client.post("/v1/hunts", json=hunt_body(), headers=observer.headers)
    assert forbidden.status_code == 403
    assert forbidden.json() == {
        "detail": "This action requires the 'hunts:write' permission.",
        "code": "forbidden",
        "required": "hunts:write",
    }


def test_delete_is_204_and_honours_if_match_when_sent(
    client: TestClient, analyst: LoggedIn
) -> None:
    hunt = create(client, analyst)

    stale = client.delete(
        f"/v1/hunts/{hunt['id']}", headers={**analyst.headers, "If-Match": '"v9"'}
    )
    assert stale.status_code == 412

    gone = client.delete(f"/v1/hunts/{hunt['id']}", headers=analyst.headers)
    assert gone.status_code == 204
    assert gone.content == b""

    assert client.get(f"/v1/hunts/{hunt['id']}", headers=analyst.headers).status_code == 404
    assert client.delete(f"/v1/hunts/{hunt['id']}", headers=analyst.headers).status_code == 404


def test_admin_touch_makes_the_next_patch_fail(client: TestClient, analyst: LoggedIn) -> None:
    hunt = create(client, analyst)

    touched = client.post(f"/v1/__admin/hunts/{hunt['id']}/touch", headers=ADMIN)
    assert touched.status_code == 200
    assert touched.json() == {"version": 2}

    response = client.patch(
        f"/v1/hunts/{hunt['id']}",
        json={"name": "Renamed"},
        headers={**analyst.headers, "If-Match": '"v1"'},
    )
    assert response.status_code == 412
    assert response.json()["current"]["version"] == 2


def test_admin_touch_of_an_unknown_hunt_is_404(client: TestClient) -> None:
    response = client.post("/v1/__admin/hunts/hnt_nope/touch", headers=ADMIN)

    assert response.status_code == 404
    assert response.json()["code"] == "hunt_not_found"


def test_admin_reset_clears_hunts(client: TestClient, analyst: LoggedIn) -> None:
    create(client, analyst)

    assert client.post("/v1/__admin/reset", headers=ADMIN).status_code == 204

    after = do_login(client, *ANALYST)
    assert client.get("/v1/hunts", headers=after.headers).json() == {"items": []}
