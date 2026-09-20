import pytest

from capture_api.platform.observer import FamilyLog, Observer
from capture_api.world.clock import FakeTimeSource
from tests.conftest import ANALYST, OBSERVER
from tests.realtime.asgi import call, login, open_stream, running
from tests.realtime.conftest import BRANCH, DENIED, HQ, AppFactory, Script, detection

STREAM = "/v1/stream/detections"


async def test_the_stream_opens_with_a_retry_hint_and_the_head_seq(make_app: AppFactory) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            assert stream.status == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            assert stream.headers["cache-control"] == "no-cache"
            assert stream.headers["x-accel-buffering"] == "no"
            opened = await stream.next_frame()

    assert opened is not None
    assert opened.comment == "open last_seq=5"
    assert opened.retry == 3_000


async def test_live_detections_arrive_once_and_in_order(
    make_app: AppFactory, fake_time: FakeTimeSource
) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            await stream.next_frame()
            fake_time.advance(25)
            first = await stream.next_frame()
            second = await stream.next_frame()

    assert first is not None
    assert second is not None
    assert [first.event, second.event] == ["detection", "detection"]
    assert [first.id, second.id] == ["6", "7"]
    assert first.payload["seq"] == 6
    assert first.payload["sensor_id"] == HQ
    assert second.payload["sensor_id"] == BRANCH


async def test_a_resume_point_replays_the_ring(make_app: AppFactory) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, {**headers, "Last-Event-ID": "3"}) as stream:
            opened = await stream.next_frame()
            replayed = [await stream.next_frame(), await stream.next_frame()]

    assert opened is not None
    assert opened.comment == "open last_seq=5"
    assert [frame.id for frame in replayed if frame] == ["4", "5"]


async def test_the_query_parameter_resumes_when_the_header_is_absent(
    make_app: AppFactory,
) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, f"{STREAM}?last_event_id=4", headers) as stream:
            await stream.next_frame()
            replayed = await stream.next_frame()

    assert replayed is not None
    assert replayed.id == "5"


async def test_the_header_wins_over_the_query_parameter(make_app: AppFactory) -> None:
    async with running(make_app()) as app:
        headers = {**(await login(app, *ANALYST)), "Last-Event-ID": "4"}
        async with open_stream(app, f"{STREAM}?last_event_id=1", headers) as stream:
            await stream.next_frame()
            replayed = await stream.next_frame()

    assert replayed is not None
    assert replayed.id == "5"


async def test_a_resume_point_older_than_the_ring_resets(
    make_app: AppFactory, epoch_ms: int
) -> None:
    history = tuple(detection(i + 1, epoch_ms - (1_200 - i) * 1_000) for i in range(1_200))

    async with running(make_app(world_script=Script(history, ()))) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, {**headers, "Last-Event-ID": "7"}) as stream:
            await stream.next_frame()
            reset = await stream.next_frame()

    assert reset is not None
    assert reset.event == "reset"
    assert reset.payload == {"reason": "resume_point_too_old", "oldest_seq": 201, "last_seq": 1200}


async def test_a_replay_skips_sensors_the_caller_cannot_read(
    make_app: AppFactory, epoch_ms: int
) -> None:
    script = Script(
        (
            detection(1, epoch_ms - 3_000, sensor_id=HQ),
            detection(2, epoch_ms - 2_000, sensor_id=DENIED),
            detection(3, epoch_ms - 1_000, sensor_id=BRANCH),
        ),
        (),
    )

    async with running(make_app(world_script=script)) as app:
        headers = await login(app, *OBSERVER)
        async with open_stream(app, STREAM, {**headers, "Last-Event-ID": "1"}) as stream:
            await stream.next_frame()
            replayed = await stream.next_frame()

    assert replayed is not None
    assert replayed.id == "3"


async def test_a_sensor_filter_narrows_the_live_feed(
    make_app: AppFactory, fake_time: FakeTimeSource
) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, f"{STREAM}?sensor_ids={BRANCH}", headers) as stream:
            await stream.next_frame()
            fake_time.advance(25)
            first = await stream.next_frame()

    assert first is not None
    assert first.id == "7"
    assert first.payload["sensor_id"] == BRANCH


async def test_an_expiring_token_ends_the_stream_with_reauth(
    make_app: AppFactory, fake_time: FakeTimeSource
) -> None:
    async with running(make_app(access_ttl_s=30)) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            await stream.next_frame()
            fake_time.advance(31)
            reauth = await stream.next_frame()
            remaining = await stream.rest()

    assert reauth is not None
    assert reauth.event == "reauth"
    assert reauth.payload == {"reason": "token_expired"}
    assert remaining == []


async def test_the_server_rotates_the_stream(
    make_app: AppFactory, fake_time: FakeTimeSource
) -> None:
    async with running(make_app(chaos="storm", access_ttl_s=600)) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            opened = await stream.next_frame()
            fake_time.advance(21)
            remaining = await stream.rest()

    assert opened is not None
    assert opened.comment == "open last_seq=5"
    assert remaining == []


async def test_revoking_the_family_closes_the_stream_without_an_event(
    make_app: AppFactory,
) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            await stream.next_frame()
            status, _body = await call(app, "POST", "/v1/auth/logout", headers=headers)
            assert status == 204
            remaining = await stream.rest()

    assert remaining == []


async def test_an_unreadable_sensor_is_refused_before_the_stream_starts(
    make_app: AppFactory,
) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *OBSERVER)

        status, body = await call(app, "GET", f"{STREAM}?sensor_ids={DENIED}", headers=headers)

    assert status == 403
    assert isinstance(body, dict)
    assert body["code"] == "forbidden_sensor"


async def test_an_idle_stream_is_kept_alive(
    make_app: AppFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fastapi.routing._PING_INTERVAL", 0.05)

    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, headers) as stream:
            await stream.next_frame()
            keepalive = await stream.next_frame()

    assert keepalive is not None
    assert keepalive.comment == "ping"


async def test_the_observer_records_the_stream_lifecycle(make_app: AppFactory) -> None:
    async with running(make_app()) as app:
        headers = await login(app, *ANALYST)
        async with open_stream(app, STREAM, {**headers, "Last-Event-ID": "4"}) as stream:
            await stream.next_frame()
        observer: Observer = app.state.observer
        family = _streaming_family(observer)

    events = [(event.kind, event.resume_from, event.reason) for event in family.streams]
    assert ("sse_open", 4, None) in events
    assert ("sse_close", None, "client") in events


def _streaming_family(observer: Observer) -> FamilyLog:
    families = [family for family in observer.families() if family.streams]
    assert len(families) == 1
    return families[0]
