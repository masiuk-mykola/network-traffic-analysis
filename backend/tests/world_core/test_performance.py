import resource
import time
import tracemalloc

import pytest

from capture_api.world.catalog import BUILTIN_SENSOR_IDS

from .conftest import make_world, world_for

SCAN_BUDGET_S = 1.5
GENERATION_BUDGET_S = 6.0
RSS_BUDGET_MB = 500
_SESSION_WORLDS = ("demo", "cohort-a", "cohort-b", "budget", "memory", "demo/integration", "alpha")
"""Every seed a pytest session keeps alive at once (``tests/integration`` caches two of its
own); the RSS ceiling is per world."""


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def test_generation_and_scanning_fit_the_budget(capsys: pytest.CaptureFixture[str]) -> None:
    world = make_world("budget")
    now = world.capture_now_ms()
    started = time.process_time()
    rows = sum(world.count(s, world.data_start_ms, now + 1) for s in BUILTIN_SENSOR_IDS)
    generation = time.process_time() - started

    started = time.process_time()
    scanned = 0
    bytes_up = 0
    for sensor_id in BUILTIN_SENSOR_IDS:
        for row in world.rows(sensor_id, world.data_start_ms, now + 1):
            scanned += 1
            bytes_up += row.bytes_up
    scan = time.process_time() - started

    started = time.process_time()
    detections = len(world.detections_until(now))
    ledgers = time.process_time() - started
    rss = _rss_mb()

    with capsys.disabled():
        print(
            f"\n  rows={rows} detections={detections}"
            f" generate={generation:.2f}s scan={scan:.3f}s ledgers={ledgers:.2f}s"
            f" rss={rss:.0f}MB"
        )
    assert scanned == rows
    assert bytes_up > 0
    assert rows > 80_000
    assert generation < GENERATION_BUDGET_S
    assert scan < SCAN_BUDGET_S
    assert rss < RSS_BUDGET_MB * len(_SESSION_WORLDS)


def test_one_world_stays_well_under_the_memory_ceiling(
    capsys: pytest.CaptureFixture[str],
) -> None:
    tracemalloc.start()
    world = make_world("memory")
    now = world.capture_now_ms()
    rows = sum(world.count(s, world.data_start_ms, now + 1) for s in BUILTIN_SENSOR_IDS)
    world.detections_until(now)
    traced, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    megabytes = traced / 1024 / 1024
    with capsys.disabled():
        print(f"\n  one world: rows={rows} traced={megabytes:.0f}MB")
    assert megabytes < RSS_BUDGET_MB


def test_a_cached_block_is_returned_without_regenerating() -> None:
    world = world_for("demo")
    window = (world.epoch_ms - 3_600_000, world.epoch_ms)
    first = list(world.rows("hq-core", *window))
    started = time.process_time()
    for _ in range(50):
        assert world.count("hq-core", *window) == len(first)
    assert time.process_time() - started < 0.2
    assert next(iter(world.rows("hq-core", *window))) is first[0]
