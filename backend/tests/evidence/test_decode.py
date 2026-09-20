import hashlib
from typing import Any

import pytest

from capture_api.world.decode import build_evidence_engine, ja4_fingerprint, openssl_date
from capture_api.world.tls_profiles import BACKGROUND_CLIENT_PROFILES
from capture_api.world.types import FileSpec

from .factories import C2_PROFILE, FakeContext, make_row

PROTOCOLS = ("dns", "http", "tls", "smtp", "smb2", "ssh", "ntp", "tcp")


@pytest.fixture
def ctx() -> FakeContext:
    return FakeContext()


def walk(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk(child)]
    if isinstance(value, list):
        return [item for child in value for item in walk(child)]
    return [value]


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_payload_is_keyed_by_protocol(ctx: FakeContext, protocol: str) -> None:
    engine = build_evidence_engine(ctx)
    payload = engine.decode(make_row(protocol), "analyst")
    assert list(payload) == [protocol]
    assert isinstance(payload[protocol], dict)


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_payload_never_contains_none(ctx: FakeContext, protocol: str) -> None:
    engine = build_evidence_engine(ctx)
    payload = engine.decode(make_row(protocol), "analyst")
    assert None not in walk(payload)


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_decoding_is_deterministic(ctx: FakeContext, protocol: str) -> None:
    row = make_row(protocol)
    first = build_evidence_engine(ctx).decode(row, "analyst")
    second = build_evidence_engine(FakeContext()).decode(row, "analyst")
    assert first == second


def test_dns_matches_the_row_attributes(ctx: FakeContext) -> None:
    row = make_row("dns")
    dns = build_evidence_engine(ctx).decode(row, "analyst")["dns"]
    assert dns["query"] == {"name": "telemetry.cdn-metrics.test", "type": "A", "class": "IN"}
    assert dns["rcode"] == {"code": 0, "name": "NOERROR"}
    assert [answer["data"] for answer in dns["answers"]] == ["203.0.113.24"]
    assert dns["answers"][0]["ttl"] == 60
    assert dns["flags"]["qr"] is True


def test_nxdomain_has_no_answers_but_an_authority_record(ctx: FakeContext) -> None:
    row = make_row("dns", attrs={"dns.rcode": "NXDOMAIN", "dns.answer": ()})
    dns = build_evidence_engine(ctx).decode(row, "analyst")["dns"]
    assert dns["rcode"] == {"code": 3, "name": "NXDOMAIN"}
    assert dns["answers"] == []
    assert dns["authority"][0]["type"] == "SOA"


def test_tls_reports_the_rows_fingerprints(ctx: FakeContext) -> None:
    row = make_row("tls")
    tls = build_evidence_engine(ctx).decode(row, "analyst")["tls"]
    assert tls["ja3"] == C2_PROFILE.ja3
    assert tls["ja3_string"] == C2_PROFILE.ja3_string
    assert tls["sni"] == "telemetry.cdn-metrics.test"
    assert tls["version"] == "TLS1.2"
    leaf = tls["certificate_chain"][0]
    assert leaf["subject_cn"] == "a1b2.invalid"
    assert leaf["self_signed"] is True
    assert len(leaf["sha256"]) == 64


def test_ca_signed_certificate_chain_has_two_entries(ctx: FakeContext) -> None:
    row = make_row(
        "tls",
        attrs={
            "tls.sni": "updates.vendor.example",
            "tls.cert_cn": "updates.vendor.example",
            "tls.cert_issuer": "Example Trust Services CA",
        },
    )
    tls = build_evidence_engine(ctx).decode(row, "analyst")["tls"]
    assert len(tls["certificate_chain"]) == 2
    assert tls["certificate_chain"][0]["self_signed"] is False
    assert tls["certificate_chain"][1]["subject_cn"] == "Example Trust Services CA"


def test_certificate_sha256_is_the_hash_of_the_bytes_in_the_capture(ctx: FakeContext) -> None:
    engine = build_evidence_engine(ctx)
    row = make_row("tls")
    decoded = engine.canonical(row)  # type: ignore[attr-defined]
    assert decoded.tls is not None
    digests = [hashlib.sha256(cert).hexdigest() for cert in decoded.tls.certificates]
    assert [cert["sha256"] for cert in decoded.payload["tls"]["certificate_chain"]] == digests


def test_smtp_reports_attachments_with_hashes(ctx: FakeContext) -> None:
    row = make_row(
        "smtp",
        files=(
            FileSpec(
                name="Frachtraten-Q3-Übersicht.xlsm",
                mime="application/vnd.ms-excel.sheet.macroEnabled.12",
                size=48_112,
                source="smtp_attachment",
            ),
        ),
    )
    smtp = build_evidence_engine(ctx).decode(row, "analyst")["smtp"]
    attachment = smtp["attachments"][0]
    assert attachment["name"] == "Frachtraten-Q3-Übersicht.xlsm"
    assert attachment["size"] == 48_112
    assert len(attachment["sha256"]) == 64
    assert attachment["file_id"].startswith("f")


def test_smb2_operations_follow_the_paths(ctx: FakeContext) -> None:
    row = make_row(
        "smb2",
        src_ip="10.20.4.17",
        dst_ip="10.20.1.10",
        attrs={"smb2.path": ("\\Invoices\\2026\\a.pdf", "\\Invoices\\2026\\b.pdf")},
    )
    smb2 = build_evidence_engine(ctx).decode(row, "analyst")["smb2"]
    assert smb2["tree"] == "\\\\FS01\\finance$"
    assert smb2["user"] == "mira.balogun"
    commands = [operation["cmd"] for operation in smb2["operations"]]
    assert commands == ["TREE_CONNECT", "CREATE", "READ", "CLOSE", "CREATE", "READ", "CLOSE"]
    assert all(isinstance(operation["bytes"], str) for operation in smb2["operations"])


def test_denied_tree_connect_carries_the_status(ctx: FakeContext) -> None:
    row = make_row(
        "smb2",
        attrs={
            "smb2.tree": "\\\\FS01\\hr$",
            "smb2.path": (),
            "smb2.status": "STATUS_ACCESS_DENIED",
        },
    )
    smb2 = build_evidence_engine(ctx).decode(row, "analyst")["smb2"]
    assert smb2["operations"] == [
        {
            "cmd": "TREE_CONNECT",
            "path": "\\\\FS01\\hr$",
            "status": "STATUS_ACCESS_DENIED",
            "bytes": "0",
            "request_ts": smb2["operations"][0]["request_ts"],
            "response_ts": smb2["operations"][0]["response_ts"],
        }
    ]


def test_ssh_resolves_the_profile_behind_the_hassh(ctx: FakeContext) -> None:
    row = make_row("ssh", dst_ip="10.20.1.10")
    ssh = build_evidence_engine(ctx).decode(row, "analyst")["ssh"]
    assert ssh["client_version"].startswith("SSH-2.0-")
    assert ssh["hassh"] == row.attr("ssh.hassh")
    assert ssh["kex_algorithms"]


def _v1(ctx: FakeContext, protocol: str) -> dict[str, Any]:
    row = make_row(protocol, sensor_id="harbor-branch")
    payload: dict[str, Any] = build_evidence_engine(ctx).decode(row, "analyst")[protocol]
    return payload


def test_v1_turns_numbers_into_strings(ctx: FakeContext) -> None:
    dns = _v1(ctx, "dns")
    assert dns["answers"]["ttl"] == "60"
    assert isinstance(dns["transaction_id"], str)


def test_v1_collapses_the_rcode_to_its_numeric_string(ctx: FakeContext) -> None:
    assert _v1(ctx, "dns")["rcode"] == "0"
    row = make_row("dns", sensor_id="harbor-branch", attrs={"dns.rcode": "NXDOMAIN"})
    assert build_evidence_engine(ctx).decode(row, "analyst")["dns"]["rcode"] == "3"


def test_v1_unwraps_single_element_arrays(ctx: FakeContext) -> None:
    dns = _v1(ctx, "dns")
    assert isinstance(dns["answers"], dict)
    tls = _v1(ctx, "tls")
    assert isinstance(tls["certificate_chain"], dict)
    assert isinstance(tls["alpn"], str | list)


def test_v1_omits_false_booleans(ctx: FakeContext) -> None:
    dns = _v1(ctx, "dns")
    assert "tc" not in dns["flags"]
    assert dns["flags"]["qr"] is True
    tls = _v1(ctx, "tls")
    assert "resumed" not in tls
    assert "self_signed" in tls["certificate_chain"]


def test_v1_turns_http_headers_into_an_object_map(ctx: FakeContext) -> None:
    http = _v1(ctx, "http")
    assert isinstance(http["request_headers"], dict)
    assert http["request_headers"]["Host"] == "198.51.100.77"
    assert isinstance(http["response_headers"], dict)
    assert http["status"] == "200"


def test_repeated_v1_headers_become_a_list() -> None:
    ctx = FakeContext()
    engine = build_evidence_engine(ctx)
    for ordinal in range(60):
        row = make_row("http", sensor_id="harbor-branch", row_id=ordinal + 1)
        headers = engine.decode(row, "analyst")["http"]["response_headers"]
        if isinstance(headers.get("Set-Cookie"), list):
            assert len(headers["Set-Cookie"]) == 2
            return
    pytest.fail("no session produced two Set-Cookie headers")


def test_observer_loses_the_smb2_user(ctx: FakeContext) -> None:
    row = make_row("smb2")
    assert build_evidence_engine(ctx).decode(row, "observer")["smb2"]["user"] == {"redacted": True}


def test_observer_loses_smtp_recipients(ctx: FakeContext) -> None:
    row = make_row("smtp")
    smtp = build_evidence_engine(ctx).decode(row, "observer")["smtp"]
    assert smtp["rcpt_to"] == [{"redacted": True}]
    assert smtp["mail_from"] == "billing@quillmere-frieght.example"


def test_observer_loses_sensitive_http_headers() -> None:
    ctx = FakeContext()
    engine = build_evidence_engine(ctx)
    for ordinal in range(60):
        row = make_row("http", row_id=ordinal + 1)
        analyst = engine.decode(row, "analyst")["http"]["request_headers"]
        names = {header["name"] for header in analyst}
        if "Cookie" not in names:
            continue
        observer = engine.decode(row, "observer")["http"]["request_headers"]
        redacted = {
            header["name"]: header["value"]
            for header in observer
            if header["value"] == {"redacted": True}
        }
        assert "Cookie" in redacted
        plain = [header for header in observer if header["name"] == "Host"]
        assert all(header["value"] != {"redacted": True} for header in plain)
        return
    pytest.fail("no session carried a Cookie header")


def test_observer_redaction_also_works_on_the_v1_header_map() -> None:
    ctx = FakeContext()
    engine = build_evidence_engine(ctx)
    for ordinal in range(60):
        row = make_row("http", sensor_id="harbor-branch", row_id=ordinal + 1)
        headers = engine.decode(row, "observer")["http"]["request_headers"]
        if "Cookie" in headers:
            assert headers["Cookie"] == {"redacted": True}
            assert headers["Host"] == "198.51.100.77"
            return
    pytest.fail("no session carried a Cookie header")


def _sample(ctx: FakeContext, protocol: str, key: str, count: int = 200) -> int:
    engine = build_evidence_engine(ctx)
    return sum(
        key in engine.decode(make_row(protocol, row_id=ordinal + 1), "analyst")[protocol]
        for ordinal in range(count)
    )


def test_undeclared_fields_appear_on_a_subset(ctx: FakeContext) -> None:
    assert 0 < _sample(ctx, "tls", "ja4") < 200
    assert 0 < _sample(ctx, "http", "x_forwarded_for") < 200
    assert 0 < _sample(ctx, "dns", "edns") < 200


def test_ja4_shape() -> None:
    fingerprint = ja4_fingerprint(BACKGROUND_CLIENT_PROFILES[0])
    head, digest_b, digest_c = fingerprint.split("_")
    assert head.startswith("t13d")
    assert len(digest_b) == 12
    assert len(digest_c) == 12


def test_openssl_date_pads_single_digit_days() -> None:
    assert openssl_date(1_762_164_000_000) == "Nov  3 10:00:00 2025 GMT"
