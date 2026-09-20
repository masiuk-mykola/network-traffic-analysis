import time
from collections.abc import Callable

from fastapi.testclient import TestClient

from capture_api.workspace.bot import TeammateBot
from capture_api.workspace.cases import CaseStore
from capture_api.world.clock import FakeTimeSource
from tests.conftest import ANALYST, LoggedIn, do_login


def app_bot(client: TestClient) -> TeammateBot:
    bot = client.app.state.bot  # type: ignore[attr-defined]
    assert isinstance(bot, TeammateBot)
    return bot


def hand_built(client: TestClient, fake_time: FakeTimeSource) -> TeammateBot:
    cases = client.app.state.cases  # type: ignore[attr-defined]
    assert isinstance(cases, CaseStore)
    return TeammateBot(cases, fake_time)


def test_the_bot_is_off_when_the_setting_says_so(client: TestClient) -> None:
    assert app_bot(client).enabled is False


def test_full_history_disables_the_bot(make_client: Callable[..., TestClient]) -> None:
    assert app_bot(make_client(teammate_bot=True, full_history=True)).enabled is False


def test_the_bot_is_enabled_when_asked_for(make_client: Callable[..., TestClient]) -> None:
    bot = app_bot(make_client(teammate_bot=True))

    assert bot.enabled is True
    assert bot.case_id == "CASE-0002"
    assert bot.interval_s == 90.0


def test_the_background_loop_edits_the_case_on_its_own(
    make_client: Callable[..., TestClient], fake_time: FakeTimeSource
) -> None:
    client = make_client(teammate_bot=True, access_ttl_s=3600)
    auth = do_login(client, *ANALYST)
    before = client.get("/v1/cases/CASE-0002", headers=auth.headers).json()["version"]

    fake_time.advance(90)
    deadline = time.monotonic() + 10
    version = before
    while version == before and time.monotonic() < deadline:
        time.sleep(0.1)
        version = client.get("/v1/cases/CASE-0002", headers=auth.headers).json()["version"]

    assert version == before + 1
    assert app_bot(client).edits == 1


def test_ninety_seconds_of_clock_produce_exactly_one_edit(
    client: TestClient, fake_time: FakeTimeSource
) -> None:
    bot = hand_built(client, fake_time)

    fake_time.advance(89)
    assert bot.tick() == 0

    fake_time.advance(2)
    assert bot.tick() == 1
    assert bot.edits == 1


def test_the_edits_cycle_note_summary_severity(
    client: TestClient, analyst: LoggedIn, fake_time: FakeTimeSource
) -> None:
    bot = hand_built(client, fake_time)
    before = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()

    bot.edit()
    after_note = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()
    assert len(after_note["notes"]) == len(before["notes"]) + 1
    assert after_note["notes"][-1]["author_id"] == "sam"
    assert after_note["version"] == before["version"] + 1

    bot.edit()
    after_summary = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()
    assert after_summary["summary"] != before["summary"]

    bot.edit()
    after_severity = client.get("/v1/cases/CASE-0002", headers=analyst.headers).json()
    assert after_severity["severity"] != before["severity"]
    assert after_severity["version"] == before["version"] + 3


def test_a_client_holding_an_old_etag_gets_412(
    client: TestClient, analyst: LoggedIn, fake_time: FakeTimeSource
) -> None:
    bot = hand_built(client, fake_time)
    tag = client.get("/v1/cases/CASE-0002", headers=analyst.headers).headers["ETag"]

    fake_time.advance(90)
    assert bot.tick() == 1
    fresh = do_login(client, *ANALYST)

    conflict = client.patch(
        "/v1/cases/CASE-0002",
        json={"status": "in_progress"},
        headers={**fresh.headers, "If-Match": tag},
    )
    assert conflict.status_code == 412
    assert conflict.json()["code"] == "etag_mismatch"
    assert conflict.headers["ETag"] != tag

    retry = client.patch(
        "/v1/cases/CASE-0002",
        json={"status": "in_progress"},
        headers={**fresh.headers, "If-Match": conflict.headers["ETag"]},
    )
    assert retry.status_code == 200


def test_a_long_clock_jump_does_not_spam_the_case(
    client: TestClient, fake_time: FakeTimeSource
) -> None:
    bot = hand_built(client, fake_time)

    fake_time.advance(10_000)

    assert bot.tick() == 5
    assert bot.tick() == 0


def test_reset_restarts_the_schedule(client: TestClient, fake_time: FakeTimeSource) -> None:
    bot = hand_built(client, fake_time)
    fake_time.advance(90)
    bot.tick()

    bot.reset()

    assert bot.edits == 0
    assert bot.tick() == 0
