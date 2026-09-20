from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from capture_api.settings import Settings, get_settings


def test_defaults_match_the_spec() -> None:
    s = Settings(_env_file=None)
    assert s.seed == "demo"
    assert s.epoch == datetime(2025, 10, 27, 12, 0, tzinfo=UTC)
    assert (s.host, s.port) == ("127.0.0.1", 8700)
    assert (s.access_ttl_s, s.refresh_idle_s, s.refresh_max_s) == (90, 1800, 28800)
    assert s.chaos == "calm"
    assert s.admin_token == "lf-dev-admin"
    assert s.allowed_origins == ("http://localhost:3000",)
    assert s.full_history is False
    assert s.teammate_bot is True
    assert s.log_level == "info"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAP_SEED", "alpha")
    monkeypatch.setenv("CAP_PORT", "9900")
    monkeypatch.setenv("CAP_FULL_HISTORY", "1")
    monkeypatch.setenv("CAP_CHAOS", "storm")
    monkeypatch.setenv("CAP_ALLOWED_ORIGINS", "http://localhost:3000, http://localhost:3001/")
    s = get_settings()
    assert s.seed == "alpha"
    assert s.port == 9900
    assert s.full_history is True
    assert s.chaos == "storm"
    assert s.allowed_origins == ("http://localhost:3000", "http://localhost:3001")
    assert get_settings() is s


def test_epoch_is_normalised_to_utc_and_must_be_aware() -> None:
    s = Settings(_env_file=None, epoch="2025-10-27T14:00:00.123456+02:00")
    assert s.epoch == datetime(2025, 10, 27, 12, 0, 0, 123000, tzinfo=UTC)
    assert s.epoch_ms == 1_761_566_400_123
    with pytest.raises(ValidationError):
        Settings(_env_file=None, epoch="2025-10-27T12:00:00")


def test_invalid_chaos_profile_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, chaos="hurricane")


def test_cursor_secret_is_derived_from_the_seed_unless_given() -> None:
    a1 = Settings(_env_file=None, seed="a")
    a2 = Settings(_env_file=None, seed="a")
    b = Settings(_env_file=None, seed="b")
    assert a1.cursor_secret == a2.cursor_secret != b.cursor_secret
    assert len(a1.cursor_secret) == 64
    assert Settings(_env_file=None, cursor_secret="k").cursor_key == b"k"


def test_teammate_bot_is_off_with_full_history() -> None:
    assert Settings(_env_file=None).teammate_bot_enabled
    assert not Settings(_env_file=None, full_history=True).teammate_bot_enabled
    assert not Settings(_env_file=None, teammate_bot=False).teammate_bot_enabled
