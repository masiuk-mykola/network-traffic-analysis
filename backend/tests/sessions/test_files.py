import hashlib
from collections.abc import Callable

import httpx2
from fastapi.testclient import TestClient

from capture_api.world.world import SimWorld
from tests.conftest import OBSERVER, LoggedIn

from .conftest import Carved, Catalog, parse_content_disposition


def _download(client: TestClient, headers: dict[str, str], file: Carved) -> httpx2.Response:
    return client.get(f"/v1/sessions/{file.session_id}/files/{file.file_id}", headers=headers)


def test_streams_the_file_with_a_checksum_and_no_content_length(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    file = rows.plain_file

    response = _download(client, login().headers, file)

    assert response.status_code == 200
    assert response.headers["content-type"] == file.spec.mime
    assert "content-length" not in response.headers, "downloads are chunked"
    assert len(response.content) == file.spec.size
    assert response.headers["x-content-sha256"] == hashlib.sha256(response.content).hexdigest()
    carved = world.file(file.file_id)
    assert carved is not None
    assert response.headers["x-content-sha256"] == carved.sha256


def test_the_content_disposition_carries_both_names(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    file = rows.plain_file

    response = _download(client, login().headers, file)

    names = parse_content_disposition(response.headers["content-disposition"])
    assert response.headers["content-disposition"].startswith("attachment;")
    assert names["filename*"] == file.spec.name
    assert names["filename"] == file.spec.name


def test_a_non_ascii_name_survives_in_filename_star_only(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    file = rows.non_ascii

    response = _download(client, login().headers, file)

    names = parse_content_disposition(response.headers["content-disposition"])
    assert not file.spec.name.isascii()
    assert names["filename*"] == file.spec.name
    assert names["filename"].isascii()
    assert names["filename"] != file.spec.name
    assert "_" in names["filename"]


def test_a_name_with_path_separators_is_safe_in_the_ascii_fallback(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    file = rows.path_separators

    response = _download(client, login().headers, file)

    header = response.headers["content-disposition"]
    names = parse_content_disposition(header)
    assert "\\" in file.spec.name or "/" in file.spec.name
    assert names["filename*"] == file.spec.name, "the raw name is still recoverable"
    assert "/" not in names["filename"]
    assert "\\" not in names["filename"]
    assert '"' not in names["filename"]
    assert header.count('"') == 2, "the fallback cannot break out of its quotes"


def test_the_trap_file_answers_200_with_a_json_error(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    file = rows.trap

    response = _download(client, login().headers, file)

    assert response.status_code == 200, "the trap is a 200; only the body says it failed"
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": "extraction_failed"}
    assert "content-disposition" not in response.headers


def test_a_purged_file_is_gone(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    file = rows.purged

    response = _download(client, login().headers, file)

    assert response.status_code == 410
    assert response.json()["code"] == "file_purged"


def test_the_session_and_the_file_must_belong_together(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    mine, other = rows.plain_file, rows.non_ascii

    unknown = client.get(f"/v1/sessions/{mine.session_id}/files/f{mine.row.id}-99", headers=headers)
    mismatched = client.get(
        f"/v1/sessions/{mine.session_id}/files/{other.file_id}", headers=headers
    )
    malformed = client.get(f"/v1/sessions/{mine.session_id}/files/nope", headers=headers)

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "file_not_found"
    assert mismatched.status_code == 404
    assert malformed.status_code == 404


def test_an_observer_may_not_download_files(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    response = _download(client, login(*OBSERVER).headers, rows.plain_file)

    assert response.status_code == 403
    assert response.json() == {
        "detail": "This action requires the 'files:download' permission.",
        "code": "forbidden",
        "required": "files:download",
    }


def test_the_eleventh_download_of_a_minute_is_refused(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    file = rows.plain_file

    for _ in range(10):
        assert _download(client, headers, file).status_code == 200

    response = _download(client, headers, file)

    assert response.status_code == 429
    assert response.json()["code"] == "download_rate_limited"
    assert int(response.headers["retry-after"]) >= 1
