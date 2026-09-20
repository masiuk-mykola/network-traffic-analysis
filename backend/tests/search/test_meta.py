from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.world.catalog import BUILTIN_SENSOR_IDS, FIELD_DEFS
from tests.conftest import LoggedIn


def test_fields_publish_the_whole_catalogue(client: TestClient, headers: dict[str, str]) -> None:
    body = client.get("/v1/meta/fields", headers=headers).json()
    names = [item["name"] for item in body["items"]]
    assert names == [definition.name for definition in FIELD_DEFS]
    sensor = next(item for item in body["items"] if item["name"] == "sensor")
    assert set(BUILTIN_SENSOR_IDS) <= set(sensor["enum"])


def test_fields_omit_absent_optionals(client: TestClient, headers: dict[str, str]) -> None:
    body = client.get("/v1/meta/fields", headers=headers).json()
    protocol = next(item for item in body["items"] if item["name"] == "protocol")
    assert "pattern" not in protocol
    assert protocol["operators"] == ["eq"]


def test_columns_are_in_default_order_and_include_the_undocumented_type(
    client: TestClient, headers: dict[str, str]
) -> None:
    items = client.get("/v1/meta/columns", headers=headers).json()["items"]
    assert [item["key"] for item in items][:5] == ["start", "sensor", "src", "dst", "protocol"]
    assert any(item["type"] == "geo_hint" for item in items)
    assert any(item["default_visible"] is False for item in items)


def test_enum_values(client: TestClient, headers: dict[str, str]) -> None:
    body = client.get("/v1/meta/enums/protocol", headers=headers).json()
    assert body["name"] == "protocol"
    assert {"value": "dns", "label": "DNS"} in body["values"]


def test_unknown_enum_is_404(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/v1/meta/enums/colour", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "unknown_enum"


def test_the_first_country_call_of_a_family_is_503_catalog_warming(
    client: TestClient, headers: dict[str, str]
) -> None:
    first = client.get("/v1/meta/enums/country", headers=headers)
    assert first.status_code == 503
    assert first.json()["code"] == "catalog_warming"
    assert first.headers["Retry-After"] == "2"

    second = client.get("/v1/meta/enums/country", headers=headers)
    assert second.status_code == 200
    assert any(value["value"] == "PT" for value in second.json()["values"])


def test_each_family_warms_the_country_catalogue_once(
    client: TestClient, headers: dict[str, str], login: Callable[..., LoggedIn]
) -> None:
    assert client.get("/v1/meta/enums/country", headers=headers).status_code == 503
    assert client.get("/v1/meta/enums/country", headers=headers).status_code == 200
    other = login()
    assert client.get("/v1/meta/enums/country", headers=other.headers).status_code == 503
    assert client.get("/v1/meta/enums/country", headers=other.headers).status_code == 200


def test_protocol_schema(client: TestClient, headers: dict[str, str]) -> None:
    body = client.get("/v1/meta/schema/dns", headers=headers).json()
    assert body["protocol"] == "dns"
    assert body["decoder_versions"] == ["v1", "v2"]
    paths = {field["path"] for field in body["fields"]}
    assert "dns.query.name" in paths
    assert "dns.edns.client_subnet" not in paths


def test_unknown_protocol_schema_is_404(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/v1/meta/schema/gopher", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "unknown_protocol"


def test_meta_needs_a_token(client: TestClient) -> None:
    assert client.get("/v1/meta/fields").status_code == 401
    assert client.get("/v1/meta/columns").status_code == 401
