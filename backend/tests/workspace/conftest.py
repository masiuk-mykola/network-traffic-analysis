import hashlib
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from capture_api.main import create_app
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource
from capture_api.world.pcap import build_pcap
from capture_api.world.types import Row
from tests.conftest import ANALYST, OBSERVER, TEAMMATE, LoggedIn, do_login

EPOCH_MS = 1_761_566_400_000
"""``2025-10-27T12:00:00Z`` — the default ``CAP_EPOCH``."""


@pytest.fixture
def analyst(client: TestClient) -> LoggedIn:
    return do_login(client, *ANALYST)


@pytest.fixture
def observer(client: TestClient) -> LoggedIn:
    return do_login(client, *OBSERVER)


@pytest.fixture
def teammate(client: TestClient) -> LoggedIn:
    return do_login(client, *TEAMMATE)


@pytest.fixture
def make_client(fake_time: FakeTimeSource) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def build(**overrides: Any) -> TestClient:
        values: dict[str, Any] = {"seed": "test", "teammate_bot": False, **overrides}
        settings = Settings(_env_file=None, **values)
        started = TestClient(create_app(settings, time_source=fake_time))
        started.__enter__()
        clients.append(started)
        return started

    yield build
    for started in reversed(clients):
        started.__exit__(None, None, None)


def hunt_query(**overrides: Any) -> dict[str, Any]:
    query: dict[str, Any] = {
        "sensor_ids": ["hq-core"],
        "window": {"preset": "24h"},
        "filter": {"all": [{"field": "protocol", "op": "eq", "value": "dns"}]},
        "sort": "-ts",
    }
    query.update(overrides)
    return query


def hunt_body(name: str = "Branch beacons", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "query": hunt_query()}
    body.update(overrides)
    return body


def sample_row(
    start_ms: int = EPOCH_MS - 3_600_000, row_id: int = (1 << 56) | (7 << 20) | 3
) -> Row:
    return Row(
        id=row_id,
        sensor_id="hq-core",
        start_ms=start_ms,
        end_ms=start_ms + 1_200,
        protocol="dns",
        transport="udp",
        src_ip="10.20.4.17",
        src_port=49_312,
        dst_ip="10.20.0.53",
        dst_port=53,
        bytes_up=86,
        bytes_down=140,
        packets_up=1,
        packets_down=1,
        risk_score=4,
        risk_reasons=(),
        summary="A static.example.com",
        attrs={
            "dns.query.name": "static.example.com",
            "dns.query.type": "A",
            "dns.rcode": "NOERROR",
        },
    )


def sample_capture(start_ms: int = EPOCH_MS - 3_600_000) -> bytes:
    decoded = {
        "dns": {
            "query": {"name": "static.example.com", "type": "A", "class": "IN"},
            "rcode": {"code": 0, "name": "NOERROR"},
            "answers": [
                {"name": "static.example.com", "type": "A", "ttl": 300, "data": "192.0.2.10"}
            ],
        }
    }
    return build_pcap(sample_row(start_ms), decoded)


def upload(
    data: bytes,
    *,
    label: str = "Branch tap 2025-10",
    tz: str = "Europe/Lisbon",
    sha256: str | None = None,
    filename: str = "capture.pcap",
) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest() if sha256 is None else sha256
    return {
        "files": {"file": (filename, data, "application/vnd.tcpdump.pcap")},
        "data": {"meta": json.dumps({"label": label, "tz": tz, "sha256": digest})},
    }
