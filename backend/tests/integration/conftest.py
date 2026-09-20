from collections.abc import Iterator
from functools import lru_cache

import pytest

from capture_api.settings import Settings
from capture_api.world.catalog import BUILTIN_SENSOR_IDS
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import AttrValue, Row
from capture_api.world.world import SimWorld, build_world


@lru_cache(maxsize=4)
def world_for(seed: str) -> SimWorld:
    settings = Settings(_env_file=None, seed=seed, teammate_bot=False)
    return build_world(settings, CaptureClock(settings.epoch, FakeTimeSource()))


def all_rows(world: SimWorld) -> Iterator[Row]:
    for sensor_id in BUILTIN_SENSOR_IDS:
        yield from world.rows(sensor_id, world.data_start_ms, world.capture_now_ms() + 1)


def values(row: Row, key: str) -> tuple[str, ...]:
    value: AttrValue | None = row.attr(key)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return (str(value),)


@pytest.fixture(scope="session")
def demo() -> SimWorld:
    return world_for("demo")


@pytest.fixture(scope="session")
def alpha() -> SimWorld:
    return world_for("alpha")
