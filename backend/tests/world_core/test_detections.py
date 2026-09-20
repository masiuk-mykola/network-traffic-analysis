import collections
from itertools import pairwise

import pytest

from capture_api.world.catalog import BUILTIN_SENSORS, DETECTION_RULES
from capture_api.world.detections import release_ms
from capture_api.world.types import DetectionData
from capture_api.world.world import SimWorld

from .conftest import SEEDS, make_world, world_for
from .test_incident import tuple_attr

LAG = {sensor.id: sensor.lag_s for sensor in BUILTIN_SENSORS}


def released(world: SimWorld) -> list[DetectionData]:
    return list(world.detections_until(world.capture_now_ms()))


def test_detection_volume_and_rule_mix() -> None:
    world = world_for("demo")
    items = released(world)
    assert 5_000 <= len(items) <= 8_000
    rules = collections.Counter(item.rule_id for item in items)
    assert set(rules) <= set(DETECTION_RULES)
    assert rules["lookalike_sender"] == 1
    assert rules["smb_mass_read"] == 1
    assert 200 <= rules["port_scan"] <= 900
    assert rules["periodic_tls_beacon"] > 500
    background = sum(
        rules[rule] for rule in ("cleartext_credentials", "rare_user_agent", "dns_tunnel_suspected")
    )
    assert 3_000 <= background <= 5_500


@pytest.mark.parametrize("seed", SEEDS)
def test_seq_is_dense_ascending_and_ordered_by_time(seed: str) -> None:
    items = released(world_for(seed))
    assert [item.seq for item in items] == list(range(1, len(items) + 1))
    assert all(a.ts_ms <= b.ts_ms for a, b in pairwise(items))
    assert len({item.id for item in items}) == len(items)


def test_seq_is_stable_across_restarts() -> None:
    first = released(world_for("demo"))
    second = released(make_world("demo"))
    assert [(d.seq, d.id, d.ts_ms) for d in first] == [(d.seq, d.id, d.ts_ms) for d in second]


def test_a_detection_is_never_released_before_its_session_is_visible() -> None:
    world = world_for("demo")
    for detection in released(world):
        row = world.raw_row(detection.session_id)
        assert row is not None
        assert detection.ts_ms >= row.start_ms + LAG[row.sensor_id] * 1000
        assert detection.sensor_id == row.sensor_id
        assert (detection.src_ip, detection.dst_ip) == (row.src_ip, row.dst_ip)
        assert detection.rule_id in tuple_attr(row, "detection.rule")


def test_the_released_prefix_grows_with_the_cut() -> None:
    world = world_for("demo")
    early = world.detections_until(world.epoch_ms - 36 * 3_600_000)
    late = world.detections_until(world.epoch_ms)
    assert 0 < len(early) < len(late)
    assert [d.seq for d in late[: len(early)]] == [d.seq for d in early]
    assert list(world.detections_after(len(early), world.epoch_ms)) == list(late[len(early) :])
    assert list(world.detections_after(len(late), world.epoch_ms)) == []


def test_detections_for_row_matches_the_ledger() -> None:
    world = world_for("demo")
    truth = world.truth()
    mail = world.row(truth.email_session_id)
    assert mail is not None
    found = world.detections_for_row(mail)
    assert [d.rule_id for d in found] == ["lookalike_sender"]
    assert found[0].severity == "medium"
    assert found[0] in released(world)
    assert world.row(found[0].session_id) is mail


def test_release_time_is_deterministic_and_bounded() -> None:
    world = world_for("demo")
    row = next(iter(world.rows("hq-core", world.data_start_ms, world.epoch_ms)))
    first = release_ms("demo", row, 2, "port_scan")
    assert first == release_ms("demo", row, 2, "port_scan")
    assert first != release_ms("demo", row, 2, "rare_user_agent")
    assert row.start_ms + 2_000 < first <= row.start_ms + 2_000 + 30_000


def test_every_detection_projects_to_the_api_model() -> None:
    world = world_for("demo")
    items = released(world)
    for detection in (items[0], items[len(items) // 2], items[-1]):
        model = world.to_detection(detection)
        assert model.session_id == str(detection.session_id)
        assert model.rule == DETECTION_RULES[detection.rule_id].name
        assert model.mitre.technique_id.startswith("T1")
        assert model.summary
