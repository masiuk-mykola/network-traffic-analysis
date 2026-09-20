from itertools import pairwise

import pytest

from capture_api.world.decode import build_evidence_engine
from capture_api.world.flows import flow_samples

from .factories import SEED, FakeContext, make_row

BUCKETS = (100, 1_000, 5_000, 60_000)


@pytest.mark.parametrize("bucket_ms", BUCKETS)
def test_totals_match_the_row(bucket_ms: int) -> None:
    row = make_row("tls", duration_ms=45_000, bytes_up=1_120, bytes_down=3_240)
    samples = flow_samples(row, bucket_ms, seed=SEED)
    assert sum(sample.bytes_up for sample in samples) == row.bytes_up
    assert sum(sample.bytes_down for sample in samples) == row.bytes_down
    assert sum(sample.packets_up for sample in samples) == row.packets_up
    assert sum(sample.packets_down for sample in samples) == row.packets_down


@pytest.mark.parametrize("bucket_ms", BUCKETS)
def test_samples_are_ascending_aligned_and_non_empty(bucket_ms: int) -> None:
    row = make_row("http", duration_ms=120_000, bytes_up=4_000_000, bytes_down=9_000)
    samples = flow_samples(row, bucket_ms, seed=SEED)
    assert samples
    times = [sample.t_ms for sample in samples]
    assert times == sorted(times)
    assert len(set(times)) == len(times)
    assert all(sample.t_ms % bucket_ms == 0 for sample in samples)
    assert all(
        sample.bytes_up or sample.bytes_down or sample.packets_up or sample.packets_down
        for sample in samples
    )


def test_empty_buckets_are_omitted() -> None:
    row = make_row("tls", duration_ms=600_000, bytes_up=1_100, bytes_down=3_200)
    samples = flow_samples(row, 1_000, seed=SEED)
    assert len(samples) < row.duration_ms // 1_000


def test_a_beacon_bursts_at_the_start() -> None:
    row = make_row("tls", duration_ms=30_000, tag="incident.beacon")
    samples = flow_samples(row, 1_000, seed=SEED)
    assert len(samples) <= 6
    assert samples[0].t_ms - (row.start_ms - row.start_ms % 1_000) == 0
    assert samples[0].bytes_up >= samples[-1].bytes_up


def test_exfiltration_is_a_sustained_upload() -> None:
    row = make_row(
        "tls",
        duration_ms=240_000,
        bytes_up=5_000_000,
        bytes_down=40_000,
        packets_up=4_000,
        packets_down=900,
        tag="incident.exfil",
    )
    samples = flow_samples(row, 1_000, seed=SEED)
    assert len(samples) >= 24
    busy = [sample for sample in samples if sample.bytes_up > 0]
    assert len(busy) >= len(samples) - 2
    assert busy[len(busy) // 2].bytes_up > 0


def test_a_long_session_has_idle_gaps() -> None:
    row = make_row("ssh", duration_ms=900_000, bytes_up=40_000, bytes_down=90_000)
    samples = flow_samples(row, 1_000, seed=SEED)
    gaps = [later.t_ms - earlier.t_ms for earlier, later in pairwise(samples)]
    assert any(gap > 1_000 for gap in gaps)


def test_flow_is_deterministic_and_reachable_through_the_engine() -> None:
    row = make_row("tls", duration_ms=45_000)
    engine = build_evidence_engine(FakeContext())
    assert list(engine.flow(row, 1_000)) == list(flow_samples(row, 1_000, seed=SEED))
    assert list(engine.flow(row, 1_000)) == list(engine.flow(row, 1_000))


def test_zero_length_session_still_produces_a_bucket() -> None:
    row = make_row("dns", duration_ms=0)
    samples = flow_samples(row, 1_000, seed=SEED)
    assert len(samples) == 1
    assert samples[0].bytes_up == row.bytes_up


def test_a_non_positive_bucket_is_rejected() -> None:
    with pytest.raises(ValueError, match="bucket_ms"):
        flow_samples(make_row("dns"), 0, seed=SEED)
