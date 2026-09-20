from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from capture_api.main import create_app
from capture_api.settings import ChaosProfile, Settings
from capture_api.world.clock import FakeTimeSource

ADMIN_TOKEN = "lf-dev-admin"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}

type ClientFactory = Callable[..., TestClient]


@pytest.fixture
def make_client(fake_time: FakeTimeSource) -> Iterator[ClientFactory]:
    clients: list[TestClient] = []

    def build(chaos: ChaosProfile = "calm", **overrides: Any) -> TestClient:
        settings = Settings(
            _env_file=None, seed="test", teammate_bot=False, chaos=chaos, **overrides
        )
        client = TestClient(create_app(settings, time_source=fake_time))
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in reversed(clients):
        client.__exit__(None, None, None)
