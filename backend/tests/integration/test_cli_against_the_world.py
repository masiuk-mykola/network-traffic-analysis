import json
from pathlib import Path

import pytest

from capture_api.__main__ import main as cli_main

LIBPCAP_MAGICS = (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1")
PCAP_HEADER_BYTES = 24


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "out"


def test_make_samples_builds_a_capture_every_session_can_render(out: Path) -> None:
    assert cli_main(["make-samples", "--out", str(out), "--seed", "samples", "--size-mb", "2"]) == 0

    capture = out / "lab-capture.pcap"
    assert capture.read_bytes()[:4] in LIBPCAP_MAGICS
    assert capture.stat().st_size > 2 * 1024 * 1024

    bad = out / "not-a-capture.pcap"
    assert bad.exists()
    assert bad.read_bytes()[:4] not in LIBPCAP_MAGICS


def test_export_fixtures_covers_every_protocol_in_both_decoder_shapes(out: Path) -> None:
    assert cli_main(["export-fixtures", "--seed", "fixtures", "--out", str(out)]) == 0

    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["seed"] == "fixtures"

    protocols = {path.name.split(".")[0] for path in (out / "sessions").glob("*.json")}
    assert {"dns", "http", "tls", "smtp", "smb2", "ssh", "ntp", "tcp"} <= protocols
    assert {path.name.split(".")[0] for path in (out / "schema").glob("*.json")} == protocols

    for path in (out / "sessions").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["decoded"], path.name
        assert int(payload["id"]) > 2**53, path.name

    assert json.loads((out / "fields.json").read_text(encoding="utf-8"))["items"]
    assert json.loads((out / "columns.json").read_text(encoding="utf-8"))["items"]
    assert json.loads((out / "rows.json").read_text(encoding="utf-8"))["items"]


def test_the_v1_dns_fixture_keeps_the_collapsed_single_answer_trap(out: Path) -> None:
    assert cli_main(["export-fixtures", "--seed", "fixtures", "--out", str(out)]) == 0
    payload = json.loads((out / "sessions" / "dns.v1.json").read_text(encoding="utf-8"))
    assert isinstance(payload["decoded"]["dns"]["answers"], dict)
