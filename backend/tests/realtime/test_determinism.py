from capture_api.platform.tokens import TokenStore
from capture_api.realtime.bus import DetectionBus
from capture_api.settings import Settings
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import DetectionData
from capture_api.world.world import build_world

AHEAD_S = 900


def boot(seed: str) -> tuple[FakeTimeSource, DetectionBus]:
    time_source = FakeTimeSource()
    settings = Settings(_env_file=None, seed=seed)
    world = build_world(settings, CaptureClock(settings.epoch, time_source))
    tokens = TokenStore(
        seed=seed,
        time_source=time_source,
        access_ttl=lambda: 90.0,
        refresh_idle_s=1_800,
        refresh_max_s=28_800,
    )
    return time_source, DetectionBus(world=lambda: world, tokens=tokens)


def released_ahead(seed: str) -> list[DetectionData]:
    time_source, bus = boot(seed)
    bus.refresh()
    time_source.advance(AHEAD_S)
    return list(bus.refresh())


def identity(detections: list[DetectionData]) -> list[tuple[int, str, int, str]]:
    return [(d.seq, d.id, d.ts_ms, d.rule_id) for d in detections]


def test_the_live_feed_is_identical_after_a_restart() -> None:
    first = released_ahead("demo")
    second = released_ahead("demo")

    assert first
    assert identity(first) == identity(second)
    assert [d.seq for d in first] == sorted(d.seq for d in first)


def test_another_seed_releases_another_feed() -> None:
    assert identity(released_ahead("demo")) != identity(released_ahead("cohort-a"))
