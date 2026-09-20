import json

import pytest

from capture_api.domain.models import SessionRow
from capture_api.settings import Settings
from capture_api.world.catalog import DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import PcapStatus, Row
from capture_api.world.views import decoder_string
from capture_api.world.world import PCAP_RETENTION_MS, PendingEngine, SimWorld, build_world

from .conftest import history, world_for

HOUR_MS = 3_600_000


def a_row(world: SimWorld, sensor_id: str) -> Row:
    return next(iter(world.rows(sensor_id, world.epoch_ms - 3 * HOUR_MS, world.epoch_ms)))


def test_sensors_and_their_visibility_cut() -> None:
    world = world_for("demo")
    assert [s.id for s in world.sensors()] == [HQ_CORE, DC_EAST, HARBOR_BRANCH]
    assert world.sensor("nope") is None
    now = world.capture_now_ms()
    assert world.visible_until_ms(HQ_CORE) == now - 2_000
    assert world.visible_until_ms(DC_EAST) == now - 1_000
    assert world.visible_until_ms(HARBOR_BRANCH) == now - 300_000
    for sensor_id in (HQ_CORE, DC_EAST, HARBOR_BRANCH):
        newest = max(history(world, sensor_id), key=lambda r: r.start_ms)
        assert newest.start_ms <= world.visible_until_ms(sensor_id)


def test_rows_of_an_unknown_sensor_are_empty() -> None:
    world = world_for("demo")
    assert list(world.rows("nope", world.data_start_ms, world.epoch_ms)) == []
    assert world.count("nope", world.data_start_ms, world.epoch_ms) == 0


def test_row_lookup_respects_visibility() -> None:
    world = world_for("demo")
    row = a_row(world, HQ_CORE)
    assert world.row(row.id) is row
    assert world.raw_row(row.id) is row
    assert world.row((9 << 56) | (row.id & ((1 << 56) - 1))) is None
    assert world.row(row.id | ((1 << 20) - 1)) is None
    hour = (world.epoch_ms - world.clock.id_base_ms) // HOUR_MS
    future = max(
        world._generator.block(HARBOR_BRANCH, hour),
        key=lambda r: r.start_ms,
    )
    assert future.start_ms > world.visible_until_ms(HARBOR_BRANCH)
    assert world.row(future.id) is None
    assert world.raw_row(future.id) is not None


def test_pcap_retention_is_48_hours_from_the_epoch() -> None:
    world = world_for("demo")
    cut = world.epoch_ms - PCAP_RETENTION_MS
    for row in history(world, DC_EAST):
        status = world.pcap_status(row)
        assert status.available == (row.start_ms >= cut)
        if not status.available:
            assert status == PcapStatus(False, "expired", row.start_ms + PCAP_RETENTION_MS)
    assert world.pcap_available(a_row(world, DC_EAST))


def test_carved_files_resolve_by_id() -> None:
    world = world_for("demo")
    truth = world.truth()
    mail = world.row(truth.email_session_id)
    assert mail is not None
    carved = world.files_for_row(mail)[0]
    assert world.file(carved.id) == carved
    assert len(world.file_bytes(carved)) == carved.size
    assert world.file_bytes(carved).startswith(b"PK\x03\x04")
    assert world.file("not-a-file") is None
    assert world.file(f"f{mail.id}-9") is None


def test_session_row_projection() -> None:
    world = world_for("demo")
    row = a_row(world, HARBOR_BRANCH)
    view = world.to_session_row(row)
    assert isinstance(view, SessionRow)
    assert view.id == str(row.id)
    assert view.duration_ms == row.end_ms - row.start_ms
    assert view.decoder == decoder_string(row.protocol, "v1")
    assert view.decoder.endswith("/1")
    assert view.bytes.up == row.bytes_up
    assert view.pcap_available == world.pcap_available(row)
    payload = json.loads(view.model_dump_json())
    assert payload["id"] == str(row.id)
    assert payload["start"].endswith("Z")
    assert "intel" not in payload or payload["intel"]["source"] == "OpenIntel (sim)"


def test_endpoints_resolve_hostnames_and_countries() -> None:
    world = world_for("demo")
    truth = world.truth()
    mail = world.row(truth.email_session_id)
    assert mail is not None
    view = world.to_session_row(mail)
    assert view.dst.host == "mx1.quillmere.example"
    assert view.dst.country is None
    assert view.src.host is None
    known = next(r for r in history(world, HQ_CORE) if world.host(r.dst_ip) is not None)
    dst = world.to_session_row(known).dst
    assert dst.host is not None
    if world.host(known.dst_ip).kind == "external":  # type: ignore[union-attr]
        assert dst.country is not None


def test_session_detail_carries_evidence() -> None:
    world = world_for("demo")
    truth = world.truth()
    mail = world.row(truth.email_session_id)
    assert mail is not None
    session = world.to_session(mail, "analyst")
    assert session.id == str(mail.id)
    assert [d.rule_id for d in session.detections] == ["lookalike_sender"]
    assert [f.sha256 for f in session.files] == [truth.attachment_sha256]
    assert session.pcap.available is False
    assert session.pcap.reason == "expired"
    assert isinstance(session.decoded, dict)


def test_sensor_projection_keeps_the_legacy_local_string() -> None:
    world = world_for("demo")
    harbor = world.sensor(HARBOR_BRANCH)
    assert harbor is not None
    view = world.to_sensor(harbor)
    assert view.name == "Hafenbüro Nord"
    assert view.decoder_version == "v1"
    assert view.status == "lagging"
    assert view.lag_seconds == 300
    assert view.retention.metadata_days == 30
    assert view.retention.pcap_hours == 48
    assert view.last_packet_local == "27/10/2025 12:55:00"
    assert view.last_packet_at.isoformat().endswith("+00:00")


def test_imports_become_sensors_and_can_be_cleared() -> None:
    settings = Settings(_env_file=None, seed="demo")
    world = build_world(settings, CaptureClock(settings.epoch, FakeTimeSource()))
    first = world.epoch_ms - 5 * HOUR_MS
    last = world.epoch_ms - 4 * HOUR_MS
    sensor = world.register_import(
        import_id="imp_001",
        label="Berth 7 tap",
        tz="Europe/Berlin",
        sha256="a" * 64,
        size=2_000_000,
        first_ts_ms=first,
        last_ts_ms=last,
    )
    assert sensor.id == "imp-1"
    assert sensor.index == 16
    assert sensor.kind == "import"
    assert (
        world.register_import(
            import_id="imp_001",
            label="again",
            tz="UTC",
            sha256="a" * 64,
            size=1,
            first_ts_ms=first,
            last_ts_ms=last,
        )
        is sensor
    )
    assert [s.id for s in world.sensors()][-1] == "imp-1"
    rows = list(world.rows("imp-1", world.data_start_ms, world.epoch_ms))
    assert len(rows) == 2_000_000 // 4_096
    assert all(first <= r.start_ms <= last for r in rows)
    assert len({r.id for r in rows}) == len(rows)
    assert world.visible_until_ms("imp-1") == last
    assert world.pcap_status(rows[0]) == PcapStatus(False, "not_captured")
    assert world.row(rows[0].id) is not None
    world.clear_imports()
    assert [s.id for s in world.sensors()] == [HQ_CORE, DC_EAST, HARBOR_BRANCH]
    assert list(world.rows("imp-1", world.data_start_ms, world.epoch_ms)) == []


def test_a_world_can_run_with_an_injected_engine() -> None:
    settings = Settings(_env_file=None, seed="demo")
    world = build_world(settings, CaptureClock(settings.epoch, FakeTimeSource()), PendingEngine())
    row = a_row(world, HQ_CORE)
    assert world.decoded(row, "analyst") == {}
    assert world.flow(row, 1_000) == ()
    assert world.pcap(row) == b""
    assert world.enrich("192.0.2.10").reputation == "unknown"
    assert world.protocol_schema("dns") is None
    assert world.to_session(row, "observer").decoded == {}


def test_decode_context_sees_rows_that_are_not_visible_yet() -> None:
    world = world_for("demo")
    context = world.decode_context
    assert context.seed == "demo"
    assert context.epoch_ms == world.epoch_ms
    assert context.incident() is world.incident()
    assert context.sensor(HQ_CORE) is world.sensor(HQ_CORE)
    assert context.host("10.20.0.53") is world.host("10.20.0.53")
    assert context.tls_client_profile(world.truth().c2_ja3) is not None
    assert context.tls_client_profile("0" * 32) is None
    row = a_row(world, HQ_CORE)
    assert context.row(row.id) is row


@pytest.mark.parametrize("sensor_id", [HQ_CORE, DC_EAST, HARBOR_BRANCH])
def test_counting_matches_iterating_on_arbitrary_windows(sensor_id: str) -> None:
    world = world_for("demo")
    windows = (
        (world.data_start_ms - 10 * HOUR_MS, world.data_start_ms + HOUR_MS),
        (world.epoch_ms - 90 * 60_000, world.epoch_ms - 30 * 60_000),
        (world.epoch_ms, world.epoch_ms + HOUR_MS),
    )
    for start, end in windows:
        assert world.count(sensor_id, start, end) == len(list(world.rows(sensor_id, start, end)))
