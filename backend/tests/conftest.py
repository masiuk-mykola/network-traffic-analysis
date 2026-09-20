import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.main import create_app
from capture_api.settings import Settings, get_settings
from capture_api.world.clock import FakeTimeSource

ANALYST = ("ana@quillmere.example", "demo-analyst")
OBSERVER = ("oli@quillmere.example", "demo-observer")
TEAMMATE = ("sam@quillmere.example", "demo-teammate")


@dataclass(frozen=True)
class LoggedIn:
    access_token: str
    refresh_token: str
    body: dict[str, object]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key.startswith("CAP_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_time() -> FakeTimeSource:
    return FakeTimeSource()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, seed="test", teammate_bot=False)


@pytest.fixture
def app(settings: Settings, fake_time: FakeTimeSource) -> FastAPI:
    return create_app(settings, time_source=fake_time)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def do_login(client: TestClient, email: str, password: str) -> LoggedIn:
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    return LoggedIn(body["access_token"], body["refresh_token"], body)


@pytest.fixture
def login(client: TestClient) -> Callable[..., LoggedIn]:

    def _login(email: str = ANALYST[0], password: str = ANALYST[1]) -> LoggedIn:
        return do_login(client, email, password)

    return _login
