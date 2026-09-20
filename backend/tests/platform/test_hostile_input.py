import json
import re
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from capture_api.cli import doctor
from capture_api.domain.base import iso_ms
from capture_api.domain.models import MAX_FILTER_VALUE_CHARS
from capture_api.search.compile import glob_regex
from capture_api.settings import Settings
from tests.conftest import LoggedIn

STAR_BOMB = "*" * 40 + "a"


@pytest.fixture
def headers(login: Callable[..., LoggedIn]) -> dict[str, str]:
    return login().headers


@pytest.fixture
def window(settings: Settings) -> tuple[str, str]:
    return iso_ms(settings.epoch - timedelta(hours=2)), iso_ms(settings.epoch)


def test_a_run_of_stars_collapses_to_one_wildcard() -> None:
    assert glob_regex("a**b").pattern == glob_regex("a*b").pattern
    assert glob_regex(STAR_BOMB).pattern == ".*a"
    assert glob_regex("a?*?b").pattern == "a\\...b" or glob_regex("a?*?b").match("axyzb")


def test_the_collapsed_glob_still_means_the_same_thing() -> None:
    assert glob_regex("*.example.test").fullmatch("cdn.example.test")
    assert glob_regex("**.example.test").fullmatch("cdn.example.test")
    assert not glob_regex("**.example.test").fullmatch("cdn.example.invalid")


def test_a_pathological_glob_matches_in_bounded_time() -> None:
    pattern = glob_regex("*" * 60 + "a")
    started = time.monotonic()
    assert pattern.fullmatch("b" * 200) is None
    assert time.monotonic() - started < 1.0


def test_too_many_wildcards_is_a_422_not_a_scan(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    start, end = window
    body = {
        "sensor_ids": ["hq-core"],
        "from": start,
        "to": end,
        "filter": {"field": "dns.query.name", "op": "glob", "value": "*a" * 20},
        "sort": "-ts",
    }
    response = client.post("/v1/searches", headers=headers, json=body)
    assert response.status_code == 422, response.text
    assert "wildcards" in response.text


def test_an_enormous_filter_value_is_a_422(
    client: TestClient, headers: dict[str, str], window: tuple[str, str]
) -> None:
    start, end = window
    body = {
        "sensor_ids": ["hq-core"],
        "from": start,
        "to": end,
        "filter": {
            "field": "dns.query.name",
            "op": "eq",
            "value": "x" * (MAX_FILTER_VALUE_CHARS + 1),
        },
        "sort": "-ts",
    }
    assert client.post("/v1/searches", headers=headers, json=body).status_code == 422


def _nested(depth: int) -> dict[str, Any]:
    node: Any = {"field": "src.ip", "op": "eq", "value": "10.20.4.17"}
    for _ in range(depth):
        node = {"not": node}
    return node


@pytest.mark.parametrize("depth", [800, 1_400, 5_000])
def test_a_deeply_nested_filter_is_a_422_not_a_500(
    client: TestClient, headers: dict[str, str], window: tuple[str, str], depth: int
) -> None:
    start, end = window
    body = {
        "sensor_ids": ["hq-core"],
        "from": start,
        "to": end,
        "filter": _nested(depth),
        "sort": "-ts",
    }
    response = client.post("/v1/searches", headers=headers, json=body)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/json")


def test_a_body_that_is_only_nesting_is_a_422_not_a_500(
    client: TestClient, headers: dict[str, str]
) -> None:
    payload = "[" * 2_000 + "]" * 2_000
    response = client.post(
        "/v1/searches",
        headers={**headers, "content-type": "application/json"},
        content=payload.encode(),
    )
    assert response.status_code == 422, response.text
    assert response.json()


@pytest.mark.parametrize("literal", ["1e400", "-1e400", "NaN"])
def test_a_non_finite_json_number_is_a_422_not_a_500(
    client: TestClient, headers: dict[str, str], window: tuple[str, str], literal: str
) -> None:
    _start, end = window
    payload = (
        '{"sensor_ids":["hq-core"],"from":' + literal + ',"to":"' + end + '",'
        '"filter":{"all":[]},"sort":"-ts"}'
    )
    response = client.post(
        "/v1/searches",
        headers={**headers, "content-type": "application/json"},
        content=payload.encode(),
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert json.dumps(detail)


def test_the_validation_shape_is_unchanged(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"email": "ana@quillmere.example"})
    assert response.status_code == 422
    issue = response.json()["detail"][0]
    assert issue["loc"] == ["body", "password"]
    assert set(issue) >= {"type", "loc", "msg", "input"}


@pytest.mark.parametrize(
    "payload",
    [
        b"total garbage not multipart at all",
        b'--zz\r\nContent-Disposition: form-data; name="' + b"f" * 60_000 + b'"\r\n\r\nx\r\n',
    ],
    ids=["garbage", "huge-part-header"],
)
def test_a_malformed_multipart_body_is_a_422_not_a_500(
    client: TestClient, headers: dict[str, str], payload: bytes
) -> None:
    response = client.post(
        "/v1/imports",
        headers={**headers, "content-type": "multipart/form-data; boundary=zz"},
        content=payload,
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "bad_multipart"


def test_a_truncated_but_parseable_body_still_reports_the_missing_part(
    client: TestClient, headers: dict[str, str]
) -> None:
    payload = b'--zz\r\nContent-Disposition: form-data; name="file"\r\n\r\nABC'
    response = client.post(
        "/v1/imports",
        headers={**headers, "content-type": "multipart/form-data; boundary=zz"},
        content=payload,
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "meta"]


def test_the_doctor_survives_a_tool_that_prints_no_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: "/usr/bin/true")

    class Silent:
        stdout = ""
        stderr = ""

    monkeypatch.setattr(doctor.subprocess, "run", lambda *_a, **_k: Silent())
    result = doctor._tool("uv", ("uv", "--version"), required=True)
    assert result.level == "ok"
    assert re.search(r"\S", result.detail)
