import shutil
import subprocess
from pathlib import Path

import pytest

from capture_api.world.decode import build_evidence_engine, ja4_fingerprint
from capture_api.world.tls_profiles import (
    BACKGROUND_CLIENT_PROFILES,
    VENDOR_UPDATER_PROFILE,
    TlsClientProfile,
)
from capture_api.world.types import AttrValue, Row

from .factories import C2_PROFILE, FakeContext, make_row

TSHARK = shutil.which("tshark")
CAPINFOS = shutil.which("capinfos")

pytestmark = pytest.mark.skipif(
    TSHARK is None or CAPINFOS is None, reason="tshark/capinfos are not installed"
)

TLS_CASES: list[tuple[TlsClientProfile, str, str | None]] = [
    (C2_PROFILE, "telemetry.cdn-metrics.test", "TLS1.2"),
    (VENDOR_UPDATER_PROFILE, "updates.vendor.example", "TLS1.2"),
    *[(profile, f"{profile.key}.example.net", None) for profile in BACKGROUND_CLIENT_PROFILES],
]


def run(tool: str | None, *args: str) -> str:
    assert tool is not None
    result = subprocess.run([tool, *args], capture_output=True, text=True, check=True)  # noqa: S603
    return result.stdout


def fields(path: Path, *names: str, display_filter: str | None = None) -> list[list[str]]:
    args = ["-r", str(path), "-T", "fields"]
    if display_filter:
        args += ["-Y", display_filter]
    for name in names:
        args += ["-e", name]
    output = run(TSHARK, *args)
    return [line.split("\t") for line in output.splitlines() if line.strip()]


def write(tmp_path: Path, row: Row, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(build_evidence_engine(FakeContext()).pcap(row))
    return path


@pytest.mark.parametrize(
    ("profile", "sni", "version"), TLS_CASES, ids=[case[0].key for case in TLS_CASES]
)
def test_tshark_recomputes_the_rows_ja3_ja3s_and_sni(
    tmp_path: Path, profile: TlsClientProfile, sni: str, version: str | None
) -> None:
    attrs: dict[str, AttrValue] = {
        "tls.sni": sni,
        "tls.ja3": profile.ja3,
        "tls.cert_cn": sni,
        "tls.cert_issuer": sni,
    }
    if version is not None:
        attrs["tls.version"] = version
    row = make_row("tls", attrs=attrs)
    engine = build_evidence_engine(FakeContext())
    decoded = engine.decode(row, "analyst")["tls"]
    path = write(tmp_path, row, f"{profile.key}.pcap")

    hello = fields(
        path,
        "tls.handshake.ja3",
        "tls.handshake.extensions_server_name",
        "tls.handshake.ja4",
        display_filter="tls.handshake.type == 1",
    )
    assert len(hello) == 1
    seen_ja3, seen_sni, seen_ja4 = hello[0]
    assert seen_ja3 == profile.ja3 == decoded["ja3"]
    assert seen_sni == sni == decoded["sni"]
    assert seen_ja4 == ja4_fingerprint(profile)

    server = fields(path, "tls.handshake.ja3s", display_filter="tls.handshake.type == 2")
    assert len(server) == 1
    assert server[0][0] == decoded["ja3s"]


def test_tshark_finds_no_malformed_packets(tmp_path: Path) -> None:
    for protocol in ("dns", "http", "tls", "smtp", "ssh", "ntp", "tcp"):
        path = write(tmp_path, make_row(protocol), f"{protocol}.pcap")
        assert fields(path, "frame.number", display_filter="_ws.malformed") == [], protocol


def test_tshark_reads_the_dns_transaction_back(tmp_path: Path) -> None:
    row = make_row("dns")
    path = write(tmp_path, row, "dns.pcap")
    rows = fields(
        path,
        "dns.qry.name",
        "dns.qry.type",
        "dns.a",
        "dns.resp.ttl",
        "dns.flags.rcode",
        display_filter="dns.flags.response == 1",
    )
    assert rows == [["telemetry.cdn-metrics.test", "1", "203.0.113.24", "60", "0"]]


def test_tshark_reads_an_nxdomain_answer_back(tmp_path: Path) -> None:
    row = make_row("dns", attrs={"dns.rcode": "NXDOMAIN", "dns.answer": ()})
    path = write(tmp_path, row, "nxdomain.pcap")
    rows = fields(
        path, "dns.flags.rcode", "dns.count.answers", display_filter="dns.flags.response == 1"
    )
    assert rows == [["3", "0"]]


def test_tshark_dissects_the_certificate_chain(tmp_path: Path) -> None:
    row = make_row(
        "tls",
        attrs={
            "tls.sni": "docs.example.org",
            "tls.ja3": BACKGROUND_CLIENT_PROFILES[7].ja3,
            "tls.version": "TLS1.2",
            "tls.cert_cn": "docs.example.org",
            "tls.cert_issuer": "Example Trust Services CA",
        },
    )
    path = write(tmp_path, row, "chain.pcap")
    rows = fields(
        path,
        "x509sat.printableString",
        "x509sat.uTF8String",
        "tls.handshake.certificates_length",
        display_filter="tls.handshake.type == 11",
    )
    assert len(rows) == 1
    assert "docs.example.org" in rows[0][1]
    assert "Example Trust Services CA" in rows[0][1]


def test_tshark_reads_the_http_transaction_back(tmp_path: Path) -> None:
    row = make_row("http")
    path = write(tmp_path, row, "http.pcap")
    request = fields(path, "http.request.method", "http.request.uri", display_filter="http.request")
    assert request == [["PUT", "/bkt/obj-0004821"]]
    response = fields(path, "http.response.code", display_filter="http.response")
    assert response == [["200"]]


def test_capinfos_reports_a_valid_file_with_the_expected_packet_count(tmp_path: Path) -> None:
    for protocol in ("dns", "tls", "http"):
        row = make_row(protocol)
        path = write(tmp_path, row, f"caps-{protocol}.pcap")
        expected = len(fields(path, "frame.number"))
        report = run(CAPINFOS, "-c", "-t", str(path))
        assert "File type:           Wireshark/tcpdump/... - pcap" in report
        assert f"Number of packets:   {expected}" in report
