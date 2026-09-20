import time
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.domain.base import iso_ms
from capture_api.settings import Settings
from capture_api.world.types import AttrValue, Row, World
from tests.conftest import OBSERVER, LoggedIn, do_login


@pytest.fixture
def make_row() -> Callable[..., Row]:

    def build(
        *,
        id: int = 72_057_594_037_927_936,
        sensor_id: str = "hq-core",
        start_ms: int = 1_761_566_400_000,
        duration_ms: int = 1_200,
        protocol: str = "dns",
        transport: str = "udp",
        src_ip: str = "10.20.4.17",
        src_port: int = 49_312,
        dst_ip: str = "192.0.2.10",
        dst_port: int = 53,
        bytes_up: int = 84,
        bytes_down: int = 312,
        risk_score: int = 12,
        risk_reasons: Sequence[str] = (),
        summary: str = "A static.example.com",
        attrs: Mapping[str, AttrValue] | None = None,
        **extra: Any,
    ) -> Row:
        return Row(
            id=id,
            sensor_id=sensor_id,
            start_ms=start_ms,
            end_ms=start_ms + duration_ms,
            protocol=protocol,  # type: ignore[arg-type]
            transport=transport,  # type: ignore[arg-type]
            src_ip=src_ip,
            src_port=src_port,
            dst_ip=dst_ip,
            dst_port=dst_port,
            bytes_up=bytes_up,
            bytes_down=bytes_down,
            packets_up=4,
            packets_down=4,
            risk_score=risk_score,
            risk_reasons=tuple(risk_reasons),
            summary=summary,
            attrs=dict(attrs or {}),
            **extra,
        )

    return build


@pytest.fixture
def analyst(login: Callable[..., LoggedIn]) -> LoggedIn:
    return login()


@pytest.fixture
def headers(analyst: LoggedIn) -> dict[str, str]:
    return analyst.headers


@pytest.fixture
def observer_headers(client: TestClient) -> dict[str, str]:
    return do_login(client, *OBSERVER).headers


@pytest.fixture
def window(settings: Settings) -> tuple[str, str]:
    return iso_ms(settings.epoch - timedelta(hours=2)), iso_ms(settings.epoch)


@pytest.fixture
def world(client: TestClient) -> World:
    app: FastAPI = client.app  # type: ignore[assignment]
    return app.state.world  # type: ignore[no-any-return]


def search_body(window: tuple[str, str], **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "sensor_ids": ["hq-core"],
        "from": window[0],
        "to": window[1],
        "filter": {"field": "protocol", "op": "eq", "value": "dns"},
    }
    body.update(overrides)
    return body


def create_search(
    client: TestClient, headers: dict[str, str], window: tuple[str, str], **overrides: Any
) -> dict[str, Any]:
    response = client.post("/v1/searches", headers=headers, json=search_body(window, **overrides))
    assert response.status_code == 202, response.text
    return dict(response.json())


def wait_done(
    client: TestClient, headers: dict[str, str], search_id: str, *, tries: int = 400
) -> dict[str, Any]:
    for _ in range(tries):
        response = client.get(f"/v1/searches/{search_id}", headers=headers)
        assert response.status_code == 200, response.text
        body = dict(response.json())
        if body["state"] not in ("queued", "running"):
            return body
        time.sleep(0.01)
    raise AssertionError(f"search {search_id} never finished")
