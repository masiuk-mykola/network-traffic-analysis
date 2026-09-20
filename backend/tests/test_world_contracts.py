from datetime import UTC, datetime

import pytest

from capture_api.domain.models import COLUMN_TYPES
from capture_api.world import catalog
from capture_api.world.clock import CaptureClock, FakeTimeSource, SystemTimeSource
from capture_api.world.filebytes import (
    carve_files,
    file_bytes,
    file_id,
    file_sha256,
    parse_file_id,
)
from capture_api.world.ids import (
    decode_session_id,
    encode_session_id,
    minute_index,
    minute_start_ms,
    parse_session_id,
)
from capture_api.world.ssh_profiles import SSH_CLIENT_PROFILES, ssh_client_by_hassh
from capture_api.world.tls_profiles import md5_hex
from capture_api.world.types import FileSpec, Row, Truth

EPOCH = datetime(2025, 10, 27, 12, 0, tzinfo=UTC)


def test_capture_clock_follows_the_time_source() -> None:
    fake = FakeTimeSource()
    clock = CaptureClock(EPOCH, fake)
    assert clock.now_ms() == clock.epoch_ms == 1_761_566_400_000
    assert clock.data_start_ms == clock.epoch_ms - 72 * 3_600_000
    assert clock.id_base_ms == clock.epoch_ms - 30 * 86_400_000
    fake.advance(1.5)
    assert clock.now_ms() == clock.epoch_ms + 1500
    assert clock.now() == datetime(2025, 10, 27, 12, 0, 1, 500000, tzinfo=UTC)
    assert clock.elapsed_s() == 1.5
    assert clock.wall_now().tzinfo is UTC
    with pytest.raises(ValueError, match="backwards"):
        fake.advance(-1)
    with pytest.raises(ValueError, match="aware"):
        CaptureClock(datetime(2025, 1, 1))  # noqa: DTZ001
    assert CaptureClock(EPOCH, SystemTimeSource()).now_ms() >= clock.epoch_ms


def test_session_ids_round_trip_and_exceed_2_53() -> None:
    clock = CaptureClock(EPOCH, FakeTimeSource())
    minute = minute_index(clock.epoch_ms - 60_000, clock.id_base_ms)
    assert minute == 30 * 24 * 60 - 1
    assert minute_start_ms(minute, clock.id_base_ms) == clock.epoch_ms - 60_000
    ids = [encode_session_id(3, minute, n) for n in range(3)]
    assert all(i > 2**53 for i in ids)
    assert len({float(i) for i in ids}) == 1
    assert decode_session_id(ids[2]) == (3, minute, 2)
    for bad in ((0, 1, 1), (256, 1, 1), (1, -1, 0), (1, 1, 1 << 20)):
        with pytest.raises(ValueError, match="out of range"):
            encode_session_id(*bad)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("72075232438042624", 72075232438042624),
        ("", None),
        ("0", None),
        ("0123", None),
        ("-5", None),
        ("12a", None),
        ("123", None),
        ("99999999999999999999", None),
        ("٣٤", None),
    ],
)
def test_parse_session_id(text: str, expected: int | None) -> None:
    assert parse_session_id(text) == expected


def test_catalogue() -> None:
    assert [s.id for s in catalog.BUILTIN_SENSORS] == ["hq-core", "dc-east", "harbor-branch"]
    harbor = catalog.BUILTIN_SENSORS[2]
    assert (harbor.decoder_version, harbor.status, harbor.lag_s) == ("v1", "lagging", 300)
    for name in catalog.ENUM_NAMES:
        values = catalog.enum_values(name)
        assert values, name
    assert catalog.enum_values("nope") is None
    assert catalog.risk_band(39) == "low"
    assert catalog.risk_band(40) == "medium"
    assert catalog.risk_band(70) == "high"
    assert catalog.DETECTION_RULES["smb_mass_read"].technique_id == "T1039"
    assert len(catalog.COUNTRIES) == 16


def test_filter_field_catalogue() -> None:
    names = [f.name for f in catalog.FIELD_DEFS]
    assert names == sorted(set(names), key=names.index)
    assert set(names) == {
        "sensor",
        "protocol",
        "src.ip",
        "dst.ip",
        "src.port",
        "dst.port",
        "host",
        "dst.host",
        "dst.country",
        "risk.score",
        "bytes.up",
        "bytes.down",
        "duration_ms",
        "dns.query.name",
        "dns.query.type",
        "dns.rcode",
        "http.host",
        "http.method",
        "http.status",
        "http.user_agent",
        "tls.sni",
        "tls.ja3",
        "tls.version",
        "smtp.mail_from",
        "smtp.attachment.sha256",
        "smb2.path",
        "smb2.status",
        "ssh.hassh",
        "detection.rule",
    }
    assert catalog.FIELD_DEFS_BY_NAME["src.ip"].operators == ["eq", "cidr", "exists"]
    assert catalog.FIELD_DEFS_BY_NAME["sensor"].enum == list(catalog.BUILTIN_SENSOR_IDS)
    assert catalog.FIELD_DEFS_BY_NAME["risk.score"].operators == ["gte", "lte", "between"]
    for field in catalog.FIELD_DEFS:
        assert field.operators, field.name
        assert field.example, field.name
        if field.type == "enum":
            assert field.enum, field.name


def test_column_catalogue_keeps_the_unknown_type_quirk() -> None:
    keys = [c.key for c in catalog.COLUMN_DEFS]
    assert keys[:9] == [
        "start",
        "sensor",
        "src",
        "dst",
        "protocol",
        "summary",
        "bytes",
        "duration",
        "risk",
    ]
    assert [c.key for c in catalog.COLUMN_DEFS if not c.default_visible] == [
        "id",
        "packets",
        "decoder",
        "files",
        "dst_country",
    ]
    assert [c.key for c in catalog.COLUMN_DEFS if c.sortable] == ["start", "bytes", "risk"]
    undocumented = [c for c in catalog.COLUMN_DEFS if c.type not in COLUMN_TYPES]
    assert [c.type for c in undocumented] == ["geo_hint"]


def _row(files: tuple[FileSpec, ...]) -> Row:
    return Row(
        id=encode_session_id(1, 43_000, 5),
        sensor_id="hq-core",
        start_ms=0,
        end_ms=10,
        protocol="smtp",
        transport="tcp",
        src_ip="198.51.100.7",
        src_port=40000,
        dst_ip="10.20.2.25",
        dst_port=25,
        bytes_up=1,
        bytes_down=1,
        packets_up=1,
        packets_down=1,
        risk_score=0,
        risk_reasons=(),
        summary="s",
        files=files,
    )


def test_carved_files_are_deterministic() -> None:
    spec = FileSpec(
        name="Tarifänderung-Oktober.xlsm",
        mime="application/vnd.ms-excel.sheet.macroEnabled.12",
        size=4096,
        source="smtp_attachment",
    )
    row = _row((spec, FileSpec("notes.txt", "text/plain", 64, "http_body", purged=True)))
    files = carve_files("demo", row)
    assert [f.id for f in files] == [file_id(row.id, 0), file_id(row.id, 1)]
    assert parse_file_id(files[0].id) == (row.id, 0)
    data = file_bytes("demo", files[0].id, spec.mime, spec.size)
    assert data.startswith(b"PK\x03\x04")
    assert len(data) == 4096
    assert file_sha256("demo", files[0].id, spec.mime, spec.size) == files[0].sha256
    assert carve_files("demo", row) == files
    assert carve_files("other", row)[0].sha256 != files[0].sha256
    text = file_bytes("demo", files[1].id, "text/plain", 64)
    assert text.isascii()
    assert files[1].purged
    assert row.files_count == 2
    assert row.duration_ms == 10
    assert row.attr("x") is None
    for bad in ("", "x1-0", "f1-0", "f72075232438042624-01", "f72075232438042624"):
        assert parse_file_id(bad) is None


def test_ssh_profiles() -> None:
    profile = SSH_CLIENT_PROFILES[0]
    assert profile.hassh == md5_hex(profile.hassh_string)
    assert profile.hassh_string.count(";") == 3
    assert ssh_client_by_hassh(profile.hassh) is profile
    assert ssh_client_by_hassh("0" * 32) is None
    assert len({p.hassh for p in SSH_CLIENT_PROFILES}) == len(SSH_CLIENT_PROFILES)


def test_truth_as_dict() -> None:
    truth = Truth(
        seed="demo",
        patient_zero_ip="10.20.40.17",
        patient_zero_host="ws-hb-017.quillmere.example",
        patient_zero_user="a.b",
        first_c2_session_id=encode_session_id(3, 1, 0),
        first_c2_start_ms=1_761_350_400_000,
        c2_domain="cdn-metrics.test",
        c2_ip="203.0.113.9",
        c2_sni="telemetry.cdn-metrics.test",
        c2_ja3="0" * 32,
        lookalike_domain="quillmere-frieght.example",
        attachment_name="x.xlsm",
        attachment_sha256="0" * 64,
        email_session_id=encode_session_id(1, 1, 0),
        smb_tree="\\\\FS01\\finance$",
        smb_file_count=1200,
        denied_share="\\\\FS01\\hr$",
        exfil_channel="http_put",
        exfil_start_ms=1,
        exfil_end_ms=2,
        exfil_bytes_up=3,
        exfil_session_count=4,
        q6_session_id=encode_session_id(3, 2, 0),
        q6_pcap_sha256="0" * 64,
        twelfth_beacon_session_id=encode_session_id(3, 3, 0),
        capture_gap_start_ms=5,
        capture_gap_end_ms=6,
    )
    out = truth.as_dict()
    assert out["first_c2_session_id"] == str(truth.first_c2_session_id)
    assert out["first_c2_start"] == "2025-10-25T00:00:00.000Z"
    assert out["first_c2_start_ms"] == 1_761_350_400_000
