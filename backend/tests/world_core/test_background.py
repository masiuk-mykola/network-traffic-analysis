import collections
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from capture_api.world.background import (
    BASE_ROWS_PER_HOUR,
    HOUR_MS,
    OFFICE_CURVE,
    PROTOCOL_MIX,
    WEEKEND_FACTOR,
    volume,
)
from capture_api.world.catalog import (
    DC_EAST,
    DNS_QUERY_TYPES,
    DNS_RCODES,
    HARBOR_BRANCH,
    HQ_CORE,
    HTTP_METHODS,
    RISK_REASONS,
    SMB2_STATUSES,
)
from capture_api.world.ids import decode_session_id
from capture_api.world.network import BACKUP_HOST, VENDOR_UPDATE_HOST
from capture_api.world.rng import Stream
from capture_api.world.tls_profiles import VENDOR_UPDATER_PROFILE

from .conftest import SEEDS, all_rows, digest, history, make_world, world_for

SENSOR_INDEX = {HQ_CORE: 1, DC_EAST: 2, HARBOR_BRANCH: 3}

REQUIRED_ATTRS: dict[str, tuple[str, ...]] = {
    "dns": ("dns.query.name", "dns.query.type", "dns.rcode", "dns.answer", "dns.ttl"),
    "http": ("http.host", "http.method", "http.status", "http.path", "http.user_agent"),
    "tls": ("tls.sni", "tls.ja3", "tls.version", "tls.cert_cn", "tls.cert_issuer"),
    "smtp": ("smtp.mail_from", "smtp.rcpt_to", "smtp.subject"),
    "smb2": ("smb2.tree", "smb2.path", "smb2.status"),
    "ssh": ("ssh.hassh", "ssh.server_version"),
}


def test_the_same_seed_produces_the_same_world() -> None:
    assert digest(make_world("demo")) == digest(world_for("demo"))


def test_a_different_seed_produces_a_different_world() -> None:
    assert digest(world_for("demo")) != digest(world_for("cohort-a"))
    left, right = world_for("demo").truth(), world_for("cohort-a").truth()
    assert left.patient_zero_ip != right.patient_zero_ip or left.c2_ip != right.c2_ip
    assert left.c2_ja3 != right.c2_ja3


@pytest.mark.parametrize("seed", SEEDS)
def test_session_ids_are_unique_and_beyond_double_precision(seed: str) -> None:
    world = world_for(seed)
    ids: list[int] = []
    for sensor_id, sensor_index in SENSOR_INDEX.items():
        rows = list(history(world, sensor_id))
        assert rows
        for row in rows:
            index, _minute, _ordinal = decode_session_id(row.id)
            assert index == sensor_index
        ids.extend(row.id for row in rows)
    assert len(set(ids)) == len(ids)
    assert min(ids) > 2**53
    assert len({float(i) for i in ids}) < len(ids)


def test_rows_are_ascending_and_reversible() -> None:
    world = world_for("demo")
    window = (world.epoch_ms - 6 * HOUR_MS, world.epoch_ms - 5 * HOUR_MS)
    forward = list(world.rows(HQ_CORE, *window))
    assert forward
    assert [r.start_ms for r in forward] == sorted(r.start_ms for r in forward)
    assert [r.id for r in forward] == sorted(r.id for r in forward)
    assert list(world.rows_desc(HQ_CORE, *window)) == list(reversed(forward))
    assert world.count(HQ_CORE, *window) == len(forward)


def test_volume_follows_the_diurnal_and_weekday_curve() -> None:
    stream = Stream("demo", "volume")
    night = volume(OFFICE_CURVE, 3, 2, stream)
    day = volume(OFFICE_CURVE, 11, 2, stream)
    weekend = volume(OFFICE_CURVE, 11, 6, stream)
    assert night < day
    assert weekend < day
    assert abs(weekend / day - WEEKEND_FACTOR) < 0.2
    assert sum(OFFICE_CURVE) == pytest.approx(24.0)
    assert BASE_ROWS_PER_HOUR * sum(OFFICE_CURVE) == pytest.approx(15_000, rel=0.01)


@pytest.mark.parametrize("sensor_id", list(PROTOCOL_MIX))
def test_protocol_mix_is_roughly_as_specified(sensor_id: str) -> None:
    world = world_for("demo")
    counts: collections.Counter[str] = collections.Counter(
        row.protocol for row in history(world, sensor_id) if row.tag is None
    )
    total = sum(counts.values())
    assert total > 10_000
    expected = dict(
        zip(
            ("dns", "tls", "http", "smb2", "smtp", "ssh", "ntp", "tcp"),
            PROTOCOL_MIX[sensor_id],
            strict=True,
        )
    )
    for protocol, share in expected.items():
        assert counts[protocol] / total == pytest.approx(share, abs=0.035), protocol


def test_only_hq_core_carries_smtp() -> None:
    world = world_for("demo")
    for sensor_id in (DC_EAST, HARBOR_BRANCH):
        assert not [r for r in history(world, sensor_id) if r.protocol == "smtp"]
    assert [r for r in history(world, HQ_CORE) if r.protocol == "smtp"]


def test_every_row_carries_its_indexed_attributes() -> None:
    world = world_for("demo")
    seen: set[str] = set()
    for row in all_rows(world):
        for key in REQUIRED_ATTRS.get(row.protocol, ()):
            assert key in row.attrs, (row.protocol, key, row.summary)
        seen.update(row.attrs)
        assert 0 <= row.risk_score <= 100
        assert all(code in RISK_REASONS for code in row.risk_reasons)
    assert {"detection.rule", "smtp.attachment.sha256"} <= seen


def test_attribute_values_come_from_the_catalogues() -> None:
    world = world_for("demo")
    for row in all_rows(world):
        if row.protocol == "dns":
            assert row.attrs["dns.query.type"] in DNS_QUERY_TYPES
            assert row.attrs["dns.rcode"] in DNS_RCODES
        elif row.protocol == "http":
            assert row.attrs["http.method"] in HTTP_METHODS
        elif row.protocol == "smb2":
            assert row.attrs["smb2.status"] in SMB2_STATUSES


def test_smtp_attachment_hashes_match_the_carved_files() -> None:
    world = world_for("demo")
    checked = 0
    for row in history(world, HQ_CORE):
        digests = row.attrs.get("smtp.attachment.sha256")
        if not digests:
            continue
        assert isinstance(digests, tuple)
        assert digests == tuple(f.sha256 for f in world.files_for_row(row))
        checked += 1
    assert checked > 20


def test_ipv6_traffic_exists_only_on_hq_core() -> None:
    world = world_for("demo")
    ipv6 = [r for r in history(world, HQ_CORE) if ":" in r.src_ip or ":" in r.dst_ip]
    assert ipv6
    share = len(ipv6) / sum(1 for r in history(world, HQ_CORE) if r.protocol in {"dns", "tls"})
    assert 0.005 < share < 0.06
    for sensor_id in (DC_EAST, HARBOR_BRANCH):
        assert not [r for r in history(world, sensor_id) if ":" in r.dst_ip]


def test_the_it_scanner_runs_three_bursts_a_day() -> None:
    world = world_for("demo")
    scans = [r for r in history(world, HQ_CORE) if r.tag == "herring.scan"]
    assert len(scans) > 1_500
    assert {r.src_ip for r in scans} == {world.network.scanner.ip}
    assert all(r.risk_score >= 70 and "port_scan" in r.risk_reasons for r in scans)
    hours = {(r.start_ms - world.data_start_ms) // HOUR_MS for r in scans}
    assert 7 <= len(hours) <= 12


def test_the_vendor_updater_beacons_from_many_hosts_with_one_fingerprint() -> None:
    world = world_for("demo")
    vendor = [r for r in history(world, HQ_CORE) if r.tag == "herring.vendor"]
    assert len(vendor) > 5_000
    assert {r.attrs["tls.ja3"] for r in vendor} == {VENDOR_UPDATER_PROFILE.ja3}
    assert {r.attrs["tls.sni"] for r in vendor} == {VENDOR_UPDATE_HOST}
    assert {r.attrs["tls.cert_issuer"] for r in vendor} == {"Example Trust Services CA"}
    assert len({r.src_ip for r in vendor}) == 40
    firing = {r.src_ip for r in vendor if "detection.rule" in r.attrs}
    assert len(firing) == 8


def test_the_nightly_backup_tops_any_bytes_sort() -> None:
    world = world_for("demo")
    backups = [r for r in history(world, DC_EAST) if r.tag == "herring.backup"]
    assert backups
    assert {r.attrs["tls.sni"] for r in backups} == {BACKUP_HOST}
    local = ZoneInfo("Europe/Lisbon")
    hours = {datetime.fromtimestamp(r.start_ms / 1000, UTC).astimezone(local).hour for r in backups}
    assert hours <= {1, 2}
    biggest = max(all_rows(world), key=lambda r: r.bytes_up)
    assert biggest.tag == "herring.backup"
    assert sum(r.bytes_up for r in backups) > 50_000_000_000


def test_exactly_one_trap_file_and_one_awkward_file_name() -> None:
    world = world_for("demo")
    traps = [f for row in all_rows(world) for f in row.files if f.trap]
    assert len(traps) == 1
    names = [f.name for row in all_rows(world) for f in row.files]
    assert sum(1 for name in names if "/" in name or "\\" in name) == 1
    purged = [f for row in all_rows(world) for f in row.files if f.purged]
    assert 0 < len(purged) / len(names) < 0.08
