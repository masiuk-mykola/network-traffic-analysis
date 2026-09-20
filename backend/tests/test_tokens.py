import pytest

from capture_api.errors import DomainError
from capture_api.platform.permissions import USERS, user_by_email
from capture_api.platform.tokens import ACCESS_PREFIX, REFRESH_PREFIX, TokenStore
from capture_api.world.clock import FakeTimeSource

ANA, OLI, SAM = USERS


def _store(clock: FakeTimeSource, ttl: float = 90.0) -> TokenStore:
    return TokenStore(
        seed="test",
        time_source=clock,
        access_ttl=lambda: ttl,
        refresh_idle_s=1800,
        refresh_max_s=28800,
    )


def _code(exc: pytest.ExceptionInfo[DomainError]) -> tuple[int, str]:
    return exc.value.status, exc.value.code


def test_login_mints_prefixed_tokens_and_authenticates() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    issued = store.login(ANA)
    assert issued.access_token.startswith(ACCESS_PREFIX)
    assert len(issued.access_token) == len(ACCESS_PREFIX) + 32
    assert issued.refresh_token.startswith(REFRESH_PREFIX)
    assert len(issued.refresh_token) == len(REFRESH_PREFIX) + 40
    assert (issued.access_expires_in, issued.refresh_expires_in) == (90, 1800)
    grant = store.authenticate(issued.access_token)
    assert grant.user is ANA
    assert grant.family_id == issued.family_id


def test_family_ids_are_deterministic_per_seed_and_ordinal() -> None:
    a, b = _store(FakeTimeSource()), _store(FakeTimeSource())
    ids_a = [a.login(ANA).family_id for _ in range(3)]
    ids_b = [b.login(ANA).family_id for _ in range(3)]
    assert ids_a == ids_b
    assert len(set(ids_a)) == 3
    assert all(fid.startswith("fam_") for fid in ids_a)


def test_access_token_expiry() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    issued = store.login(ANA)
    clock.advance(89.9)
    assert store.access_status(issued.access_token) == "ok"
    clock.advance(0.1)
    assert store.access_status(issued.access_token) == "token_expired"
    with pytest.raises(DomainError) as exc:
        store.authenticate(issued.access_token)
    assert _code(exc) == (401, "token_expired")
    assert exc.value.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


@pytest.mark.parametrize("token", [None, "", "at_nope", "Bearer x", "rt_" + "a" * 40])
def test_unknown_tokens_are_invalid(token: str | None) -> None:
    store = _store(FakeTimeSource())
    with pytest.raises(DomainError) as exc:
        store.authenticate(token)
    assert _code(exc) == (401, "invalid_token")


def test_refresh_rotates_and_keeps_old_access_valid_until_expiry() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    first = store.login(ANA)
    clock.advance(30)
    second = store.refresh(first.refresh_token)
    assert second.family_id == first.family_id
    assert second.access_token != first.access_token
    assert second.refresh_token != first.refresh_token
    assert store.access_status(first.access_token) == "ok"
    clock.advance(60)
    assert store.access_status(first.access_token) == "token_expired"
    assert store.access_status(second.access_token) == "ok"
    third = store.refresh(second.refresh_token)
    assert store.authenticate(third.access_token).family_id == first.family_id


def test_refresh_reuse_revokes_the_family_and_fires_callbacks() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    first = store.login(ANA)
    second = store.refresh(first.refresh_token)
    seen: list[tuple[str, str]] = []
    listened: list[str] = []
    store.on_family_revoked(first.family_id, lambda fid, reason: seen.append((fid, reason)))
    store.add_revocation_listener(lambda fid, _reason: listened.append(fid))
    with pytest.raises(DomainError) as exc:
        store.refresh(first.refresh_token)
    assert _code(exc) == (401, "refresh_reused")
    assert seen == [(first.family_id, "refresh_reused")]
    assert listened == [first.family_id]
    for token in (first.access_token, second.access_token):
        assert store.access_status(token) == "session_revoked"
    with pytest.raises(DomainError) as exc:
        store.refresh(second.refresh_token)
    assert _code(exc) == (401, "session_revoked")


def test_refresh_errors() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    with pytest.raises(DomainError) as exc:
        store.refresh("rt_" + "x" * 40)
    assert _code(exc) == (401, "refresh_invalid")
    with pytest.raises(DomainError) as exc:
        store.refresh("garbage")
    assert _code(exc) == (401, "refresh_invalid")

    idle = store.login(ANA)
    clock.advance(1801)
    with pytest.raises(DomainError) as exc:
        store.refresh(idle.refresh_token)
    assert _code(exc) == (401, "refresh_expired")


def test_family_absolute_lifetime() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    current = store.login(ANA)
    for _ in range(16):
        clock.advance(1790)
        current = store.refresh(current.refresh_token)
    assert current.refresh_expires_in < 1800
    clock.advance(1790)
    with pytest.raises(DomainError) as exc:
        store.refresh(current.refresh_token)
    assert _code(exc) == (401, "refresh_expired")


def test_logout_is_idempotent_and_accepts_expired_tokens() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    issued = store.login(ANA)
    clock.advance(500)
    assert store.logout(issued.access_token) == issued.family_id
    assert store.logout(issued.access_token) == issued.family_id
    assert store.access_status(issued.access_token) == "session_revoked"
    family = store.family(issued.family_id)
    assert family is not None
    assert family.revoked_reason == "logout"
    with pytest.raises(DomainError) as exc:
        store.logout("at_unknown")
    assert _code(exc) == (401, "invalid_token")


def test_admin_expire_and_revoke() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    ana, oli = store.login(ANA), store.login(OLI)
    assert store.expire_access_tokens("ANA@quillmere.example") == 1
    assert store.access_status(ana.access_token) == "token_expired"
    assert store.access_status(oli.access_token) == "ok"
    refreshed = store.refresh(ana.refresh_token)
    assert store.access_status(refreshed.access_token) == "ok"
    assert store.expire_access_tokens() == 2
    assert store.access_status(oli.access_token) == "token_expired"

    assert store.revoke_user("oli@quillmere.example") == 1
    assert store.access_status(oli.access_token) == "session_revoked"
    assert store.revoke_user("oli@quillmere.example") == 0
    assert store.family_count() == 1


def test_access_ttl_provider_can_change_at_runtime() -> None:
    clock = FakeTimeSource()
    ttl = [90.0]
    store = TokenStore(
        seed="t",
        time_source=clock,
        access_ttl=lambda: ttl[0],
        refresh_idle_s=1800,
        refresh_max_s=28800,
    )
    ttl[0] = 15
    issued = store.login(SAM)
    assert issued.access_expires_in == 15
    clock.advance(15)
    assert store.access_status(issued.access_token) == "token_expired"


def test_family_callbacks_unsubscribe_and_immediate_call() -> None:
    store = _store(FakeTimeSource())
    issued = store.login(ANA)
    calls: list[str] = []
    unsubscribe = store.on_family_revoked(issued.family_id, lambda _f, r: calls.append(r))
    unsubscribe()
    unsubscribe()
    store.revoke_family(issued.family_id, "admin")
    assert calls == []
    store.on_family_revoked(issued.family_id, lambda _f, r: calls.append(r))
    assert calls == ["admin"]


def test_failing_callback_does_not_block_revocation() -> None:
    store = _store(FakeTimeSource())
    issued = store.login(ANA)

    def broken(_fid: str, _reason: str) -> None:
        raise RuntimeError("boom")

    store.on_family_revoked(issued.family_id, broken)
    assert store.revoke_family(issued.family_id, "logout")
    assert store.access_status(issued.access_token) == "session_revoked"


def test_reset_and_sweep() -> None:
    clock = FakeTimeSource()
    store = _store(clock)
    issued = store.login(ANA)
    fired: list[str] = []
    store.on_family_revoked(issued.family_id, lambda _f, r: fired.append(r))
    store.reset()
    assert fired == ["reset"]
    assert store.access_status(issued.access_token) == "invalid_token"
    assert store.login(ANA).family_id == issued.family_id

    clock.advance(28800 + 91)
    assert store.sweep() == 1
    assert store.family_count(active_only=False) == 0


def test_users_lookup_is_case_insensitive() -> None:
    assert user_by_email("  Ana@Quillmere.Example ") is ANA
    assert user_by_email("nobody@quillmere.example") is None
