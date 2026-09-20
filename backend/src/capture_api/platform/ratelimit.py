import logging
import math
from collections import deque
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from capture_api.errors import DomainError
from capture_api.world.clock import TimeSource

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BucketSpec:
    name: str
    limit: int
    window_s: float
    code: str
    detail: str
    retry_after_s: int | None = None
    """Fixed ``Retry-After``; ``None`` computes it from the oldest hit in the window."""


BUCKETS: Mapping[str, BucketSpec] = {
    spec.name: spec
    for spec in (
        BucketSpec(
            name="estimate",
            limit=4,
            window_s=1.0,
            code="estimate_rate_limited",
            detail="Too many estimates; at most 4 per second.",
            retry_after_s=1,
        ),
        BucketSpec(
            name="search_create",
            limit=12,
            window_s=60.0,
            code="search_rate_limited",
            detail="Too many searches created; at most 12 per minute.",
        ),
        BucketSpec(
            name="download",
            limit=10,
            window_s=60.0,
            code="download_rate_limited",
            detail="Too many downloads; at most 10 per minute.",
        ),
        BucketSpec(
            name="analytics",
            limit=10,
            window_s=10.0,
            code="analytics_rate_limited",
            detail="Too many histogram or pivot requests; at most 10 per 10 seconds.",
        ),
        BucketSpec(
            name="enrich_batch",
            limit=1,
            window_s=1.0,
            code="enrich_rate_limited",
            detail="Too many enrichment batches; at most 1 per second.",
            retry_after_s=1,
        ),
        BucketSpec(
            name="enrich_single",
            limit=5,
            window_s=1.0,
            code="enrich_rate_limited",
            detail="Too many single-IP enrichments; at most 5 per second.",
            retry_after_s=1,
        ),
    )
}

MAX_TRACKED_KEYS = 4096


class RateLimiter:
    def __init__(
        self, time_source: TimeSource, buckets: Mapping[str, BucketSpec] | None = None
    ) -> None:
        self._time = time_source
        self._buckets = dict(buckets or BUCKETS)
        self._hits: dict[tuple[str, str], deque[float]] = {}

    @property
    def buckets(self) -> Mapping[str, BucketSpec]:
        return self._buckets

    def spec(self, bucket: str) -> BucketSpec:
        return self._buckets[bucket]

    def _window(self, bucket: str, key: str, now: float) -> deque[float]:
        spec = self._buckets[bucket]
        if len(self._hits) > MAX_TRACKED_KEYS:
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < 600}
        hits = self._hits.setdefault((bucket, key), deque())
        while hits and now - hits[0] >= spec.window_s:
            hits.popleft()
        return hits

    def hits(self, bucket: str, key: str) -> int:
        return len(self._window(bucket, key, self._time.monotonic()))

    def remaining(self, bucket: str, key: str) -> int:
        return max(0, self._buckets[bucket].limit - self.hits(bucket, key))

    def allows(self, bucket: str, key: str) -> bool:
        return self.remaining(bucket, key) > 0

    def retry_after_s(self, bucket: str, key: str) -> int:
        spec = self._buckets[bucket]
        if spec.retry_after_s is not None:
            return spec.retry_after_s
        now = self._time.monotonic()
        hits = self._window(bucket, key, now)
        if not hits:
            return 1
        return max(1, math.ceil(hits[0] + spec.window_s - now))

    def check(self, bucket: str, key: str, **extra: Any) -> None:
        now = self._time.monotonic()
        spec = self._buckets[bucket]
        hits = self._window(bucket, key, now)
        if len(hits) >= spec.limit:
            raise DomainError.rate_limited(
                spec.code, spec.detail, self.retry_after_s(bucket, key), **extra
            )
        hits.append(now)

    def record(self, bucket: str, key: str) -> None:
        self._window(bucket, key, self._time.monotonic()).append(self._time.monotonic())

    def reset(self, bucket: str | None = None) -> None:
        if bucket is None:
            self._hits.clear()
            return
        for pair in [p for p in self._hits if p[0] == bucket]:
            del self._hits[pair]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    app.state.rate_limiter = RateLimiter(app.state.time)
    try:
        yield
    finally:
        app.state.rate_limiter.reset()
