import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from capture_api.world.types import Row
from capture_api.world.world import SimWorld
from tests.integration.conftest import all_rows

TSHARK = shutil.which("tshark")

pytestmark = pytest.mark.skipif(TSHARK is None, reason="tshark is not installed")

LIBPCAP_MAGICS = (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1")


def fields(path: Path, *names: str, display_filter: str | None = None) -> list[list[str]]:
    assert TSHARK is not None
    args = [TSHARK, "-r", str(path), "-T", "fields"]
    if display_filter:
        args += ["-Y", display_filter]
    for name in names:
        args += ["-e", name]
    out = subprocess.run(args, capture_output=True, text=True, check=True)  # noqa: S603
    return [line.split("\t") for line in out.stdout.splitlines() if line.strip()]


def write(tmp_path: Path, world: SimWorld, row: Row, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(world.pcap(row))
    assert path.read_bytes()[:4] in LIBPCAP_MAGICS
    return path


def first(world: SimWorld, predicate: Callable[[Row], bool]) -> Row:
    for row in all_rows(world):
        if world.pcap_status(row).available and predicate(row):
            return row
    pytest.fail("no visible session with a retained capture matched")


def test_a_generated_dns_session_parses_and_matches_its_decoded_view(
    demo: SimWorld, tmp_path: Path
) -> None:
    row = first(demo, lambda r: r.protocol == "dns" and r.attr("dns.query.name"))
    path = write(tmp_path, demo, row, "dns.pcap")
    assert not fields(path, "frame.number", display_filter="_ws.malformed")

    payload = demo.decoded(row, "analyst")["dns"]
    seen = fields(path, "dns.qry.name", display_filter="dns")
    assert any(payload["query"]["name"] in values for values in seen)


def test_a_generated_tls_session_yields_the_rows_ja3_and_sni(
    demo: SimWorld, tmp_path: Path
) -> None:
    row = first(demo, lambda r: r.protocol == "tls" and r.attr_str("tls.sni"))
    path = write(tmp_path, demo, row, "tls.pcap")
    assert not fields(path, "frame.number", display_filter="_ws.malformed")

    payload = demo.decoded(row, "analyst")["tls"]
    hello = fields(
        path,
        "tls.handshake.ja3",
        "tls.handshake.extensions_server_name",
        display_filter="tls.handshake.type == 1",
    )
    assert hello, "no ClientHello in the capture"
    assert hello[0] == [row.attr_str("tls.ja3"), row.attr_str("tls.sni")]
    assert hello[0] == [payload["ja3"], payload["sni"]]

    server = fields(path, "tls.handshake.ja3s", display_filter="tls.handshake.type == 2")
    assert server, "no ServerHello in the capture"
    assert server[0][0] == payload["ja3s"]


def test_the_c2_beacon_capture_carries_the_incidents_fingerprint(
    demo: SimWorld, tmp_path: Path
) -> None:
    truth = demo.truth()
    row = demo.row(truth.q6_session_id)
    assert row is not None
    path = write(tmp_path, demo, row, "c2.pcap")
    assert not fields(path, "frame.number", display_filter="_ws.malformed")

    hello = fields(
        path,
        "tls.handshake.ja3",
        "tls.handshake.extensions_server_name",
        display_filter="tls.handshake.type == 1",
    )
    assert hello[0] == [truth.c2_ja3, truth.c2_sni]


def test_a_generated_http_session_parses_and_matches_its_decoded_view(
    demo: SimWorld, tmp_path: Path
) -> None:
    row = first(demo, lambda r: r.protocol == "http" and r.attr_str("http.host"))
    path = write(tmp_path, demo, row, "http.pcap")
    assert not fields(path, "frame.number", display_filter="_ws.malformed")

    payload = demo.decoded(row, "analyst")["http"]
    hosts = fields(path, "http.host", display_filter="http.request")
    assert hosts, "no HTTP request in the capture"
    assert hosts[0][0] == payload["host"]


def test_a_legacy_v1_session_still_produces_a_clean_capture(demo: SimWorld, tmp_path: Path) -> None:
    row = first(
        demo,
        lambda r: r.sensor_id == "harbor-branch" and r.protocol == "tls" and r.attr_str("tls.sni"),
    )
    assert demo.sensor("harbor-branch") is not None
    path = write(tmp_path, demo, row, "v1.pcap")
    assert not fields(path, "frame.number", display_filter="_ws.malformed")

    hello = fields(path, "tls.handshake.ja3", display_filter="tls.handshake.type == 1")
    assert hello[0][0] == row.attr_str("tls.ja3")
