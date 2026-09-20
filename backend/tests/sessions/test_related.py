from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.world.world import SimWorld
from tests.conftest import OBSERVER, LoggedIn

from .conftest import Catalog


def _walk(client: TestClient, headers: dict[str, str], session_id: str, window: str) -> list[str]:
    seen: list[str] = []
    cursor: str | None = ""
    while cursor is not None:
        query = f"window={window}" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(f"/v1/sessions/{session_id}/related?{query}", headers=headers).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
    return seen


def test_returns_other_sessions_between_the_same_pair(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    row = rows.busy
    pair = {row.src_ip, row.dst_ip}

    body = client.get(f"/v1/sessions/{row.id}/related?window=6h", headers=login().headers).json()

    assert body["items"]
    for item in body["items"]:
        assert {item["src"]["ip"], item["dst"]["ip"]} == pair
        assert item["sensor_id"] == row.sensor_id
        assert item["id"] != str(row.id)


def test_items_are_newest_first(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    body = client.get(
        f"/v1/sessions/{rows.busy.id}/related?window=6h", headers=login().headers
    ).json()

    starts = [item["start"] for item in body["items"]]
    assert starts == sorted(starts, reverse=True)


def test_a_page_holds_100_and_the_cursor_walks_the_rest(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    row = rows.busy

    first = client.get(f"/v1/sessions/{row.id}/related?window=6h", headers=headers).json()
    assert len(first["items"]) == 100
    assert first["next_cursor"] is not None

    seen = _walk(client, headers, str(row.id), "6h")

    assert len(seen) == len(set(seen))
    assert len(seen) == rows.busy_related


def test_a_narrower_window_returns_fewer_sessions(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog, world: SimWorld
) -> None:
    headers = login().headers
    row = rows.busy

    wide = _walk(client, headers, str(row.id), "6h")
    narrow = _walk(client, headers, str(row.id), "15m")

    assert set(narrow) < set(wide), "a narrower window can only drop sessions"
    for session_id in narrow:
        candidate = world.row(int(session_id))
        assert candidate is not None
        assert abs(candidate.start_ms - row.start_ms) <= 900_000


def test_a_tampered_cursor_is_refused(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    row = rows.busy
    cursor = client.get(f"/v1/sessions/{row.id}/related?window=6h", headers=headers).json()[
        "next_cursor"
    ]

    tampered = client.get(
        f"/v1/sessions/{row.id}/related?window=6h&cursor={cursor[:-2]}AA", headers=headers
    )
    nonsense = client.get(
        f"/v1/sessions/{row.id}/related?window=6h&cursor=not-a-cursor", headers=headers
    )

    assert tampered.status_code == 400
    assert tampered.json()["code"] == "invalid_cursor"
    assert nonsense.status_code == 400


def test_a_cursor_is_bound_to_its_window_and_session(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    headers = login().headers
    row = rows.busy
    cursor = client.get(f"/v1/sessions/{row.id}/related?window=6h", headers=headers).json()[
        "next_cursor"
    ]

    other_window = client.get(
        f"/v1/sessions/{row.id}/related?window=1h&cursor={cursor}", headers=headers
    )
    other_session = client.get(
        f"/v1/sessions/{rows.plain_file.row.id}/related?window=6h&cursor={cursor}",
        headers=headers,
    )

    assert other_window.status_code == 400
    assert other_window.json()["code"] == "invalid_cursor"
    assert other_session.status_code == 400


def test_an_unknown_window_is_a_422(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    response = client.get(f"/v1/sessions/{rows.busy.id}/related?window=2h", headers=login().headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "window"]


def test_404_and_403_match_the_detail_route(
    client: TestClient, login: Callable[..., LoggedIn], rows: Catalog
) -> None:
    assert client.get("/v1/sessions/nope/related", headers=login().headers).status_code == 404
    forbidden = client.get(
        f"/v1/sessions/{rows.dc_east.id}/related", headers=login(*OBSERVER).headers
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden_sensor"
