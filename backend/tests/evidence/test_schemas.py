from typing import Any

import pytest

from capture_api.world.decode import build_evidence_engine
from capture_api.world.schemas import (
    PROTOCOL_SCHEMAS,
    SCHEMA_PROTOCOLS,
    UNDECLARED_PATHS,
    declared_paths,
    protocol_schema,
)
from capture_api.world.tls_profiles import BACKGROUND_CLIENT_PROFILES
from capture_api.world.types import FileSpec, Row

from .factories import FakeContext, make_row


def resolve(payload: Any, path: str) -> list[Any]:
    current: list[Any] = [payload]
    for raw in path.split("."):
        key = raw.removesuffix("[]")
        nested = [item[key] for item in current if isinstance(item, dict) and key in item]
        if raw.endswith("[]"):
            nested = [entry for item in nested if isinstance(item, list) for entry in item]
        current = nested
    return current


def samples() -> list[Row]:
    attachment = FileSpec(
        name="Frachtraten-Q3-Übersicht.xlsm",
        mime="application/vnd.ms-excel.sheet.macroEnabled.12",
        size=48_112,
        source="smtp_attachment",
    )
    download = FileSpec(
        name="price-list.pdf", mime="application/pdf", size=91_000, source="http_body"
    )
    return [
        make_row("dns"),
        make_row("dns", attrs={"dns.rcode": "NXDOMAIN", "dns.answer": ()}),
        make_row(
            "dns",
            attrs={
                "dns.query.type": "MX",
                "dns.query.name": "quillmere.example",
                "dns.answer": ("mx1.quillmere.example",),
            },
        ),
        make_row("http", files=(download,)),
        make_row("http", attrs={"http.method": "GET", "http.status": 404}),
        make_row(
            "tls",
            attrs={
                "tls.sni": "docs.example.org",
                "tls.ja3": BACKGROUND_CLIENT_PROFILES[0].ja3,
                "tls.version": "TLS1.3",
                "tls.cert_cn": "docs.example.org",
                "tls.cert_issuer": "Example Trust Services CA",
            },
        ),
        make_row("smtp", files=(attachment,)),
        make_row("smb2"),
        make_row("ssh"),
        make_row("ntp"),
        make_row("tcp"),
    ]


@pytest.mark.parametrize("protocol", SCHEMA_PROTOCOLS)
def test_every_protocol_has_a_schema(protocol: str) -> None:
    schema = protocol_schema(protocol)
    assert schema is not None
    assert schema.protocol == protocol
    assert schema.decoder_versions == ["v1", "v2"]
    assert schema.fields


def test_unknown_protocol_has_no_schema() -> None:
    assert protocol_schema("quic") is None
    assert declared_paths("quic") == ()


@pytest.mark.parametrize("protocol", SCHEMA_PROTOCOLS)
def test_paths_start_with_the_protocol_and_are_unique(protocol: str) -> None:
    paths = declared_paths(protocol)
    assert len(set(paths)) == len(paths)
    assert all(path.split(".")[0] == path.split("[")[0].split(".")[0] for path in paths)
    assert all(path.startswith(f"{protocol}.") for path in paths)


def test_the_three_undeclared_fields_are_not_declared() -> None:
    every = {field.path for schema in PROTOCOL_SCHEMAS.values() for field in schema.fields}
    for path in UNDECLARED_PATHS:
        assert path not in every
    assert not any(path.startswith("dns.edns") for path in every)


def test_sensitive_flag_marks_the_redacted_values() -> None:
    sensitive = {
        field.path
        for schema in PROTOCOL_SCHEMAS.values()
        for field in schema.fields
        if field.sensitive
    }
    assert {"smtp.rcpt_to[]", "smb2.user"} <= sensitive
    assert "http.request_headers[].value" in sensitive


def test_every_declared_path_appears_in_a_real_payload() -> None:
    ctx = FakeContext()
    engine = build_evidence_engine(ctx)
    payloads = [engine.decode(row, "analyst") for row in samples()]
    missing = [
        path
        for protocol in SCHEMA_PROTOCOLS
        for path in declared_paths(protocol)
        if not any(resolve(payload, path) for payload in payloads)
    ]
    assert missing == []


def test_undeclared_fields_really_are_emitted() -> None:
    ctx = FakeContext()
    engine = build_evidence_engine(ctx)
    payloads = [
        engine.decode(make_row(protocol, row_id=ordinal + 1), "analyst")
        for protocol in ("tls", "http", "dns")
        for ordinal in range(120)
    ]
    for path in UNDECLARED_PATHS:
        assert any(resolve(payload, path) for payload in payloads), path
