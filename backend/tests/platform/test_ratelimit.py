import pytest

from capture_api.errors import DomainError
from capture_api.platform.ratelimit import BUCKETS, RateLimiter
from capture_api.world.clock import FakeTimeSource

from .conftest import ClientFactory


@pytest.fixture
def clock() -> FakeTimeSource:
    return FakeTimeSource()


@pytest.fixture
def limiter(clock: FakeTimeSource) -> RateLimiter:
    return RateLimiter(clock)


@pytest.mark.parametrize(
    ("bucket", "limit", "window_s", "code"),
    [
        ("estimate", 4, 1.0, "estimate_rate_limited"),
        ("search_create", 12, 60.0, "search_rate_limited"),
        ("download", 10, 60.0, "download_rate_limited"),
        ("analytics", 10, 10.0, "analytics_rate_limited"),
        ("enrich_batch", 1, 1.0, "enrich_rate_limited"),
        ("enrich_single", 5, 1.0, "enrich_rate_limited"),
    ],
)
def test_bucket_limits(
    limiter: RateLimiter,
    clock: FakeTimeSource,
    *,
    bucket: str,
    limit: int,
    window_s: float,
    code: str,
) -> None:
    assert BUCKETS[bucket].limit == limit
    assert BUCKETS[bucket].window_s == window_s
    for _ in range(limit):
        limiter.check(bucket, "fam_a")
    with pytest.raises(DomainError) as excinfo:
        limiter.check(bucket, "fam_a")
    assert excinfo.value.status == 429
    assert excinfo.value.code == code
    assert int(excinfo.value.headers["Retry-After"]) >= 1
    clock.advance(window_s)
    limiter.check(bucket, "fam_a")


def test_windows_are_per_key(limiter: RateLimiter) -> None:
    for _ in range(4):
        limiter.check("estimate", "fam_a")
    limiter.check("estimate", "fam_b")
    assert limiter.remaining("estimate", "fam_a") == 0
    assert limiter.remaining("estimate", "fam_b") == 3


def test_the_window_slides_instead_of_resetting(
    limiter: RateLimiter, clock: FakeTimeSource
) -> None:
    for _ in range(4):
        limiter.check("estimate", "fam_a")
        clock.advance(0.2)
    with pytest.raises(DomainError):
        limiter.check("estimate", "fam_a")
    clock.advance(0.25)
    limiter.check("estimate", "fam_a")
    assert limiter.hits("estimate", "fam_a") == 4


def test_retry_after_is_computed_from_the_oldest_hit(
    limiter: RateLimiter, clock: FakeTimeSource
) -> None:
    for _ in range(10):
        limiter.check("download", "fam_a")
    clock.advance(30)
    with pytest.raises(DomainError) as excinfo:
        limiter.check("download", "fam_a")
    assert excinfo.value.headers["Retry-After"] == "30"


def test_fixed_retry_after_for_one_second_buckets(limiter: RateLimiter) -> None:
    limiter.check("enrich_batch", "fam_a")
    with pytest.raises(DomainError) as excinfo:
        limiter.check("enrich_batch", "fam_a")
    assert excinfo.value.headers["Retry-After"] == "1"


def test_extra_fields_ride_along(limiter: RateLimiter) -> None:
    for _ in range(4):
        limiter.check("estimate", "fam_a")
    with pytest.raises(DomainError) as excinfo:
        limiter.check("estimate", "fam_a", sensor_id="hq-core")
    assert excinfo.value.body()["sensor_id"] == "hq-core"


def test_allows_and_record_and_reset(limiter: RateLimiter) -> None:
    assert limiter.allows("estimate", "fam_a") is True
    for _ in range(4):
        limiter.record("estimate", "fam_a")
    assert limiter.allows("estimate", "fam_a") is False
    limiter.reset("estimate")
    assert limiter.allows("estimate", "fam_a") is True
    limiter.record("download", "fam_a")
    limiter.reset()
    assert limiter.hits("download", "fam_a") == 0


def test_the_service_is_on_app_state(make_client: ClientFactory) -> None:
    client = make_client()
    limiter = client.app.state.rate_limiter  # type: ignore[attr-defined]
    assert isinstance(limiter, RateLimiter)
    assert set(limiter.buckets) == set(BUCKETS)
