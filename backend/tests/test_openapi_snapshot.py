import json
import re
from pathlib import Path
from typing import Any

import pytest

from capture_api.cli.openapi import DEFAULT_OUT, render_openapi

SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi.json"

REFRESH = f"stale snapshot - refresh it with `uv run capture-api openapi --out {DEFAULT_OUT}`"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return document


def test_snapshot_is_current() -> None:
    assert SNAPSHOT.read_text(encoding="utf-8") == render_openapi(), REFRESH


def test_every_operation_id_is_camel_case(schema: dict[str, Any]) -> None:
    ids = [op["operationId"] for path in schema["paths"].values() for op in path.values()]
    assert ids
    assert len(ids) == len(set(ids))
    assert [i for i in ids if not re.fullmatch(r"[a-z]+([A-Z][a-z0-9]*)*", i)] == []


def test_recursive_models_are_not_split_into_input_output_twins(schema: dict[str, Any]) -> None:
    names = schema["components"]["schemas"]
    assert "FilterNode" in names
    assert [n for n in names if n.endswith(("-Input", "-Output"))] == []


def test_admin_observer_and_websocket_routes_are_not_published(schema: dict[str, Any]) -> None:
    assert [p for p in schema["paths"] if "__admin" in p or "__observer" in p] == []
    assert "/v1/live" not in schema["paths"]
    assert "/v1/live/tickets" in schema["paths"]


def test_every_route_documents_tags_a_summary_and_its_errors(schema: dict[str, Any]) -> None:
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            assert operation.get("tags"), where
            assert operation.get("summary"), where
            if path == "/v1/health":
                continue
            errors = [code for code in operation["responses"] if code[0] in "45"]
            assert errors, where
            for code in errors:
                content = operation["responses"][code]["content"]
                assert list(content) == ["application/json"], f"{where} {code}"
