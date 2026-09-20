from fastapi.testclient import TestClient

from tests.conftest import ANALYST, OBSERVER, do_login
from tests.realtime.conftest import BRANCH, DENIED, HQ, ClientFactory, Script, detection


def test_the_newest_page_is_ascending(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    body = client.get("/v1/detections?limit=3", headers=logged.headers).json()

    assert [item["seq"] for item in body["items"]] == [3, 4, 5]
    assert body["last_seq"] == 5


def test_a_cursor_returns_only_newer_detections(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    body = client.get("/v1/detections?after_seq=3", headers=logged.headers).json()

    assert [item["seq"] for item in body["items"]] == [4, 5]


def test_the_page_carries_the_whole_detection(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    item = client.get("/v1/detections?limit=1", headers=logged.headers).json()["items"][0]

    assert item["sensor_id"] == HQ
    assert item["id"] == "det_5"
    assert item["session_id"] == str(72_057_594_037_927_936 + 5)
    assert item["mitre"]["technique_id"]
    assert item["src"]["ip"] == "10.20.4.17"


def test_an_unreadable_sensor_is_refused(client: TestClient) -> None:
    logged = do_login(client, *OBSERVER)

    response = client.get(f"/v1/detections?sensor_ids={DENIED}", headers=logged.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_sensor"
    assert response.json()["sensor_id"] == DENIED


def test_an_observer_does_not_see_an_unreadable_sensor_by_default(
    make_realtime: ClientFactory, epoch_ms: int
) -> None:
    script = Script(
        (
            detection(1, epoch_ms - 3_000, sensor_id=HQ),
            detection(2, epoch_ms - 2_000, sensor_id=DENIED),
            detection(3, epoch_ms - 1_000, sensor_id=BRANCH),
        ),
        (),
    )
    built = make_realtime(world_script=script)
    observer = do_login(built.client, *OBSERVER)
    analyst = do_login(built.client, *ANALYST)

    seen = built.client.get("/v1/detections", headers=observer.headers).json()
    everything = built.client.get("/v1/detections", headers=analyst.headers).json()

    assert [item["seq"] for item in seen["items"]] == [1, 3]
    assert seen["last_seq"] == 3
    assert [item["seq"] for item in everything["items"]] == [1, 2, 3]


def test_a_sensor_filter_narrows_the_page(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    branch = client.get(f"/v1/detections?sensor_ids={BRANCH}", headers=logged.headers).json()
    hq = client.get(f"/v1/detections?sensor_ids={HQ}", headers=logged.headers).json()

    assert branch["items"] == []
    assert len(hq["items"]) == 5


def test_the_limit_is_validated_rather_than_clamped(client: TestClient) -> None:
    logged = do_login(client, *ANALYST)

    response = client.get("/v1/detections?limit=501", headers=logged.headers)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_authentication_is_required(client: TestClient) -> None:
    assert client.get("/v1/detections").status_code == 401
