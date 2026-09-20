import math
from collections import deque
from datetime import UTC, datetime
from email.utils import format_datetime

from capture_api.errors import DomainError
from capture_api.platform.permissions import normalize_email
from capture_api.world.clock import TimeSource


class LoginLimiter:
    def __init__(
        self, time_source: TimeSource, *, max_failures: int = 5, window_s: float = 60.0
    ) -> None:
        self._time = time_source
        self._max = max_failures
        self._window = window_s
        self._failures: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        entries = self._failures.setdefault(key, deque())
        while entries and now - entries[0] >= self._window:
            entries.popleft()
        return entries

    def check(self, email: str) -> None:
        now = self._time.monotonic()
        entries = self._prune(normalize_email(email), now)
        if len(entries) < self._max:
            return
        wait_s = max(1, math.ceil(entries[0] + self._window - now))
        retry_at = datetime.fromtimestamp(math.ceil(self._time.time()) + wait_s, tz=UTC)
        raise DomainError(
            429,
            "login_rate_limited",
            "Too many failed sign-in attempts for this account; try again later.",
            headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
        )

    def record_failure(self, email: str) -> None:
        now = self._time.monotonic()
        self._prune(normalize_email(email), now).append(now)

    def record_success(self, email: str) -> None:
        self._failures.pop(normalize_email(email), None)

    def reset(self) -> None:
        self._failures.clear()
