import pytest

from capture_api.errors import DomainError
from capture_api.platform.idempotency import TTL_S, IdempotencyStore
from capture_api.world.clock import FakeTimeSource

BODY = b'{"sensor_ids": ["hq-core"], "from": "2025-10-27T00:00:00Z"}'
SAME_BODY_OTHER_ORDER = b'{"from": "2025-10-27T00:00:00Z", "sensor_ids": ["hq-core"]}'
OTHER_BODY = b'{"sensor_ids": ["dc-east"], "from": "2025-10-27T00:00:00Z"}'


@pytest.fixture
def clock() -> FakeTimeSource:
    return FakeTimeSource()


@pytest.fixture
def store(clock: FakeTimeSource) -> IdempotencyStore:
    return IdempotencyStore(clock)


@pytest.mark.parametrize("key", ["abcd1234", "a" * 64, "search-2025_10-27"])
def test_valid_keys(key: str) -> None:
    assert IdempotencyStore.validate_key(key) == key


@pytest.mark.parametrize("key", ["short", "a" * 65, "has spaces!", "nope/slash"])
def test_invalid_keys(key: str) -> None:
    with pytest.raises(DomainError) as excinfo:
        IdempotencyStore.validate_key(key)
    assert (excinfo.value.status, excinfo.value.code) == (422, "invalid_idempotency_key")


def test_no_header_means_no_key() -> None:
    assert IdempotencyStore.validate_key(None) is None


def test_key_ordering_does_not_change_the_fingerprint() -> None:
    assert IdempotencyStore.fingerprint(BODY) == IdempotencyStore.fingerprint(SAME_BODY_OTHER_ORDER)
    assert IdempotencyStore.fingerprint(BODY) != IdempotencyStore.fingerprint(OTHER_BODY)
    assert IdempotencyStore.fingerprint(b"not json") == IdempotencyStore.fingerprint("not json")


def test_first_call_misses_and_the_retry_replays(store: IdempotencyStore) -> None:
    fingerprint = store.fingerprint(BODY)
    assert store.lookup("searches", "fam_a", "key-12345", fingerprint) is None
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    hit = store.lookup("searches", "fam_a", "key-12345", fingerprint)
    assert hit is not None
    assert hit.value == "srch_1"


def test_same_key_with_another_body_is_a_mismatch(store: IdempotencyStore) -> None:
    store.remember("searches", "fam_a", "key-12345", store.fingerprint(BODY), "srch_1")
    with pytest.raises(DomainError) as excinfo:
        store.lookup("searches", "fam_a", "key-12345", store.fingerprint(OTHER_BODY))
    assert (excinfo.value.status, excinfo.value.code) == (422, "idempotency_key_mismatch")


def test_records_are_scoped_per_family_and_resource(store: IdempotencyStore) -> None:
    fingerprint = store.fingerprint(BODY)
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    assert store.lookup("searches", "fam_b", "key-12345", fingerprint) is None
    assert store.lookup("exports", "fam_a", "key-12345", fingerprint) is None


def test_records_expire_after_ten_minutes(store: IdempotencyStore, clock: FakeTimeSource) -> None:
    fingerprint = store.fingerprint(BODY)
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    clock.advance(TTL_S - 1)
    assert store.lookup("searches", "fam_a", "key-12345", fingerprint) is not None
    clock.advance(2)
    assert store.lookup("searches", "fam_a", "key-12345", fingerprint) is None
    assert len(store) == 0


def test_forget_and_reset(store: IdempotencyStore) -> None:
    fingerprint = store.fingerprint(BODY)
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    store.forget("searches", "fam_a", "key-12345")
    assert store.lookup("searches", "fam_a", "key-12345", fingerprint) is None
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    store.reset()
    assert len(store) == 0


def test_a_post_commit_fault_still_replays(store: IdempotencyStore) -> None:
    fingerprint = store.fingerprint(BODY)
    store.remember("searches", "fam_a", "key-12345", fingerprint, "srch_1")
    fault = DomainError.unavailable("unavailable", "chaos", 2)
    assert fault.status == 503
    replay = store.lookup("searches", "fam_a", "key-12345", fingerprint)
    assert replay is not None
    assert replay.value == "srch_1"
