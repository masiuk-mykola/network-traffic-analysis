import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from capture_api import main as main_module
from capture_api.__main__ import build_parser
from capture_api.__main__ import main as cli_main
from capture_api.api import auth
from capture_api.cli import COMMANDS, Command, register
from capture_api.main import ROUTER_MODULES, create_app, operation_id


def test_every_router_module_is_mounted_with_tags(app: FastAPI) -> None:
    assert len(ROUTER_MODULES) == 15
    for module in ROUTER_MODULES:
        assert module.router.tags, module.__name__
    paths = set(app.openapi()["paths"])
    assert {"/v1/auth/login", "/v1/auth/refresh", "/v1/auth/logout", "/v1/me"} <= paths


def test_operation_ids_are_camel_case(app: FastAPI) -> None:
    schema = app.openapi()
    ids = {op["operationId"] for item in schema["paths"].values() for op in item.values()}
    assert {"login", "refresh", "logout", "getMe"} <= ids
    route = next(r for r in auth.router.routes if isinstance(r, APIRoute) and r.name == "get_me")
    assert operation_id(route) == "getMe"


def test_no_cors_headers(client: TestClient) -> None:
    r = client.options(
        "/v1/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in r.headers
    assert all("CORS" not in m.cls.__name__ for m in client.app.user_middleware)  # type: ignore[attr-defined]


def test_core_services_exist_without_the_lifespan(app: FastAPI) -> None:
    for name in ("settings", "time", "clock", "tokens", "login_limiter"):
        assert getattr(app.state, name) is not None


def test_missing_providers_are_skipped_but_broken_ones_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main_module, "SERVICE_PROVIDERS", ("capture_api.does_not_exist",))
    with TestClient(create_app()) as client:
        assert client.get("/v1/me").status_code == 401
    monkeypatch.setattr(main_module, "SERVICE_PROVIDERS", ("capture_api.settings",))
    with pytest.raises(RuntimeError, match="no lifespan"), TestClient(create_app()):
        pass


def test_openapi_command_writes_the_document(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert cli_main(["openapi", "--out", str(out)]) == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["info"]["title"] == "Capture API Simulator API"
    assert "/v1/auth/login" in document["paths"]
    assert "bearer" in document["components"]["securitySchemes"]


def test_cli_lists_serve_and_openapi() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "9999", "--chaos", "flaky"])
    assert (args.port, args.chaos, args.reload) == (9999, "flaky", False)
    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--chaos", "hurricane"])


def test_cli_registry_rejects_duplicates() -> None:
    def run_a(_args: object) -> int:
        return 0

    def run_b(_args: object) -> int:
        return 1

    register(Command("dup-test", "x", lambda _p: None, run_a))  # type: ignore[arg-type]
    try:
        with pytest.raises(ValueError, match="twice"):
            register(Command("dup-test", "x", lambda _p: None, run_b))  # type: ignore[arg-type]
    finally:
        COMMANDS.pop("dup-test", None)
