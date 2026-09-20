import hashlib
from collections.abc import Iterator, Sequence
from functools import lru_cache

import pytest

from capture_api.settings import Settings
from capture_api.world.catalog import BUILTIN_SENSOR_IDS
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import Row
from capture_api.world.world import SimWorld, build_world

SEEDS: tuple[str, ...] = ("demo", "cohort-a", "cohort-b")


def make_world(seed: str) -> SimWorld:
    settings = Settings(_env_file=None, seed=seed)
    return build_world(settings, CaptureClock(settings.epoch, FakeTimeSource()))


@lru_cache(maxsize=8)
def world_for(seed: str) -> SimWorld:
    return make_world(seed)


def history(world: SimWorld, sensor_id: str) -> Iterator[Row]:
    return world.rows(sensor_id, world.data_start_ms, world.capture_now_ms() + 1)


def all_rows(world: SimWorld) -> Iterator[Row]:
    for sensor_id in BUILTIN_SENSOR_IDS:
        yield from history(world, sensor_id)


def digest(world: SimWorld) -> str:
    sponge = hashlib.blake2b(digest_size=16)
    for row in all_rows(world):
        sponge.update(
            f"{row.id}|{row.sensor_id}|{row.start_ms}|{row.end_ms}|{row.protocol}|"
            f"{row.src_ip}:{row.src_port}|{row.dst_ip}:{row.dst_port}|"
            f"{row.bytes_up}/{row.bytes_down}|{row.risk_score}|{row.summary}|"
            f"{sorted(row.attrs.items(), key=lambda kv: kv[0])}".encode()
        )
    return sponge.hexdigest()


def rows_with(rows: Sequence[Row] | Iterator[Row], key: str, value: object) -> list[Row]:
    return [row for row in rows if row.attrs.get(key) == value]


@pytest.fixture(scope="session")
def demo() -> SimWorld:
    return world_for("demo")
