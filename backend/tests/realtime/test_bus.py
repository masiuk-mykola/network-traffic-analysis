from typing import cast

import pytest

from capture_api.platform.permissions import user_by_email
from capture_api.platform.tokens import TokenStore
from capture_api.realtime.bus import RING_SIZE, DetectionBus
from capture_api.settings import Settings
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import World
from tests.realtime.conftest import BRANCH, DENIED, HQ, FakeWorld, Script, detection, make_script

SENSORS = (HQ, BRANCH, DENIED)


@pytest.fixture
def time_source() -> FakeTimeSource:
    return FakeTimeSource()


@pytest.fixture
def tokens(time_source: FakeTimeSource) -> TokenStore:
    return TokenStore(
        seed="test",
        time_source=time_source,
        access_ttl=lambda: 90.0,
        refresh_idle_s=1_800,
        refresh_max_s=28_800,
    )


@pytest.fixture
def family(tokens: TokenStore) -> str:
    user = user_by_email("ana@quillmere.example")
    assert user is not None
    return tokens.login(user).family_id


def build(
    script: Script, time_source: FakeTimeSource, tokens: TokenStore
) -> tuple[FakeWorld, DetectionBus]:
    settings = Settings(_env_file=None, seed="test")
    world = FakeWorld(CaptureClock(settings.epoch, time_source), script)
    return world, DetectionBus(world=lambda: cast(World, world), tokens=tokens)


def test_priming_loads_history_but_releases_nothing(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)
    assert bus.refresh() == ()
    assert bus.head_seq() == 5
    assert bus.oldest_seq() == 1


async def test_new_detections_reach_a_subscriber_in_order(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore, family: str
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)
    subscription = bus.subscribe(family_id=family, sensor_ids=SENSORS)
    time_source.advance(25)

    released = bus.refresh()

    assert [d.seq for d in released] == [6, 7]
    first = await subscription.next(0.01)
    second = await subscription.next(0.01)
    assert first is not None
    assert second is not None
    assert (first.seq, second.seq) == (6, 7)
    assert await subscription.next(0.01) is None


async def test_a_subscriber_only_sees_its_sensors(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore, family: str
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)
    subscription = bus.subscribe(family_id=family, sensor_ids=[BRANCH])
    time_source.advance(25)
    bus.refresh()

    first = await subscription.next(0.01)

    assert first is not None
    assert first.sensor_id == BRANCH
    assert await subscription.next(0.01) is None


def test_backfill_without_a_cursor_returns_the_newest_ascending(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)

    items, last_seq = bus.backfill(after_seq=None, limit=3, sensor_ids=SENSORS)

    assert [d.seq for d in items] == [3, 4, 5]
    assert last_seq == 5


def test_backfill_after_a_cursor_is_the_head_even_when_nothing_matches(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    script = Script((detection(1, epoch_ms - 1_000, sensor_id=DENIED),), ())
    _world, bus = build(script, time_source, tokens)

    items, last_seq = bus.backfill(after_seq=None, limit=100, sensor_ids=[HQ])

    assert items == []
    assert last_seq == 1


def test_the_ring_only_replays_the_last_thousand(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    history = tuple(detection(i + 1, epoch_ms - (1_200 - i) * 1_000) for i in range(1_200))
    _world, bus = build(Script(history, ()), time_source, tokens)

    assert bus.head_seq() == 1_200
    assert bus.oldest_seq() == 1_200 - RING_SIZE + 1
    assert len(bus.replay(0, SENSORS)) == RING_SIZE


def test_revoking_the_family_closes_its_subscriptions(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    user = user_by_email("ana@quillmere.example")
    assert user is not None
    issued = tokens.login(user)
    _world, bus = build(make_script(epoch_ms), time_source, tokens)
    subscription = bus.subscribe(family_id=issued.family_id, sensor_ids=SENSORS)

    tokens.logout(issued.access_token)

    assert subscription.closed
    assert subscription.close_reason == "revoked:logout"
    assert bus.count() == 0


def test_reset_drops_the_ring_and_closes_everything(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore, family: str
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)
    subscription = bus.subscribe(family_id=family, sensor_ids=SENSORS)
    hooks: list[str] = []
    bus.add_reset_hook(lambda: hooks.append("called"))

    bus.reset()

    assert subscription.closed
    assert hooks == ["called"]
    assert bus.count() == 0


def test_a_missing_world_is_not_an_error(tokens: TokenStore) -> None:
    bus: DetectionBus = DetectionBus(world=lambda: None, tokens=tokens)

    assert bus.refresh() == ()
    assert bus.head_seq() == 0
    assert bus.backfill(after_seq=None, limit=10, sensor_ids=SENSORS) == ([], 0)


async def test_an_unknown_family_is_closed_at_once(
    epoch_ms: int, time_source: FakeTimeSource, tokens: TokenStore
) -> None:
    _world, bus = build(make_script(epoch_ms), time_source, tokens)

    subscription = bus.subscribe(family_id="fam_gone", sensor_ids=SENSORS)

    assert subscription.closed
    assert bus.count() == 0
