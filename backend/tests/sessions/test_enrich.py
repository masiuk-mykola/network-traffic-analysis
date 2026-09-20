from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.world.world import SimWorld
from tests.conftest import LoggedIn

INTERNAL = "10.20.4.11"
EXTERNAL = "203.0.113.24"
REPUTATIONS = {"clean", "suspicious", "malicious", "unknown"}


def test_a_batch_is_keyed_by_the_address_that_was_sent(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    response = client.post(
        "/v1/enrich/ips",
        json={"ips": [EXTERNAL, INTERNAL, "192.0.2.7"]},
        headers=login().headers,
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert set(results) == {EXTERNAL, INTERNAL, "192.0.2.7"}
    assert all(entry["reputation"] in REPUTATIONS for entry in results.values())


def test_an_external_address_carries_a_documentation_asn(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    results = client.post(
        "/v1/enrich/ips", json={"ips": [EXTERNAL]}, headers=login().headers
    ).json()["results"]

    entry = results[EXTERNAL]
    assert entry["country"].isupper()
    assert len(entry["country"]) == 2
    assert 64496 <= int(entry["asn"].removeprefix("AS")) <= 64511
    assert entry["org"]


def test_an_internal_address_is_unknown_with_no_null_keys(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    results = client.post(
        "/v1/enrich/ips", json={"ips": [INTERNAL]}, headers=login().headers
    ).json()["results"]

    assert results[INTERNAL] == {"reputation": "unknown"}


def test_the_single_route_answers_the_same_object(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    headers = login().headers

    single = client.get(f"/v1/enrich/ips/{EXTERNAL}", headers=headers)
    batch = client.post("/v1/enrich/ips", json={"ips": [EXTERNAL]}, headers=headers)

    assert single.status_code == 200
    assert single.json() == batch.json()["results"][EXTERNAL]


def test_an_ipv6_peer_can_be_enriched(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    response = client.get("/v1/enrich/ips/2001:db8:ff:3::130", headers=login().headers)

    assert response.status_code == 200
    assert response.json()["reputation"] in REPUTATIONS


def test_enrichment_agrees_with_the_grid(
    client: TestClient, login: Callable[..., LoggedIn], world: SimWorld
) -> None:
    row = next(
        candidate
        for candidate in world.rows("hq-core", world.epoch_ms - 600_000, world.epoch_ms)
        if world.to_session_row(candidate).dst.country is not None
    )
    grid = world.to_session_row(row)
    headers = login().headers

    detail = client.get(f"/v1/sessions/{row.id}", headers=headers).json()
    enriched = client.get(f"/v1/enrich/ips/{row.dst_ip}", headers=headers).json()

    assert detail["dst"]["country"] == grid.dst.country
    assert enriched["country"] == detail["dst"]["country"]


def test_a_batch_is_bounded(client: TestClient, login: Callable[..., LoggedIn]) -> None:
    headers = login().headers

    empty = client.post("/v1/enrich/ips", json={"ips": []}, headers=headers)
    too_many = client.post(
        "/v1/enrich/ips", json={"ips": [f"192.0.2.{n % 256}" for n in range(101)]}, headers=headers
    )

    assert empty.status_code == 422
    assert too_many.status_code == 422
    assert too_many.json()["detail"][0]["loc"] == ["body", "ips"]


def test_a_second_batch_in_the_same_second_is_refused(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    headers = login().headers

    first = client.post("/v1/enrich/ips", json={"ips": [EXTERNAL]}, headers=headers)
    second = client.post("/v1/enrich/ips", json={"ips": [EXTERNAL]}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == "enrich_rate_limited"
    assert second.headers["retry-after"] == "1"


def test_the_single_route_allows_five_per_second(
    client: TestClient, login: Callable[..., LoggedIn]
) -> None:
    headers = login().headers

    for _ in range(5):
        assert client.get(f"/v1/enrich/ips/{EXTERNAL}", headers=headers).status_code == 200

    sixth = client.get(f"/v1/enrich/ips/{EXTERNAL}", headers=headers)

    assert sixth.status_code == 429
    assert sixth.json()["code"] == "enrich_rate_limited"


def test_needs_a_token(client: TestClient) -> None:
    assert client.get(f"/v1/enrich/ips/{EXTERNAL}").status_code == 401
    assert client.post("/v1/enrich/ips", json={"ips": [EXTERNAL]}).status_code == 401
