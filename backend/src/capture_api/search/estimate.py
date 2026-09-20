from collections.abc import Sequence
from dataclasses import dataclass

from capture_api.search.compile import Predicate
from capture_api.world.types import World

SAMPLE_TARGET = 4_000
"""How many rows an estimate evaluates, spread evenly over the requested sensors."""


@dataclass(frozen=True, slots=True)
class Estimate:
    matches: int
    scanned: int


def visible_window(world: World, sensor_id: str, from_ms: int, to_ms: int) -> tuple[int, int]:
    end = min(to_ms, world.visible_until_ms(sensor_id) + 1)
    start = max(from_ms, world.data_start_ms)
    return start, max(start, end)


def windows(
    world: World, sensor_ids: Sequence[str], from_ms: int, to_ms: int
) -> list[tuple[str, int, int]]:
    return [
        (sensor_id, *visible_window(world, sensor_id, from_ms, to_ms)) for sensor_id in sensor_ids
    ]


def total_rows(world: World, resolved: Sequence[tuple[str, int, int]]) -> int:
    return sum(world.count(sensor_id, start, end) for sensor_id, start, end in resolved)


def estimate(
    world: World,
    sensor_ids: Sequence[str],
    from_ms: int,
    to_ms: int,
    predicate: Predicate,
    *,
    sample_target: int = SAMPLE_TARGET,
) -> Estimate:
    resolved = windows(world, sensor_ids, from_ms, to_ms)
    budget = max(1, sample_target // max(1, len(resolved)))
    matches = 0
    scanned = 0
    for sensor_id, start, end in resolved:
        total = world.count(sensor_id, start, end)
        scanned += total
        if total == 0:
            continue
        step = max(1, total // budget)
        sampled = 0
        hits = 0
        for index, row in enumerate(world.rows_desc(sensor_id, start, end)):
            if index % step:
                continue
            sampled += 1
            if predicate(row):
                hits += 1
        if sampled:
            matches += round(hits * total / sampled)
    return Estimate(matches=matches, scanned=scanned)
