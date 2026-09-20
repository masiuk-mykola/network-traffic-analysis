import time
from datetime import UTC, datetime, timedelta
from typing import Protocol

HISTORY = timedelta(hours=72)
ID_BASE_OFFSET = timedelta(days=30)


class TimeSource(Protocol):
    def monotonic(self) -> float: ...

    def time(self) -> float: ...


class SystemTimeSource:
    def monotonic(self) -> float:
        return time.monotonic()

    def time(self) -> float:
        return time.time()


class FakeTimeSource:
    def __init__(self, *, wall: float = 1_761_566_400.0, monotonic: float = 1_000.0) -> None:
        self._wall = wall
        self._monotonic = monotonic

    def monotonic(self) -> float:
        return self._monotonic

    def time(self) -> float:
        return self._wall

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("time cannot go backwards")
        self._monotonic += seconds
        self._wall += seconds


class CaptureClock:
    def __init__(self, epoch: datetime, time_source: TimeSource | None = None) -> None:
        if epoch.tzinfo is None:
            raise ValueError("epoch must be timezone-aware")
        self._time: TimeSource = time_source or SystemTimeSource()
        self._epoch = epoch.astimezone(UTC)
        self._epoch_ms = int(self._epoch.timestamp() * 1000)
        self._boot = self._time.monotonic()

    @property
    def time_source(self) -> TimeSource:
        return self._time

    @property
    def epoch(self) -> datetime:
        return self._epoch

    @property
    def epoch_ms(self) -> int:
        return self._epoch_ms

    @property
    def data_start_ms(self) -> int:
        return self._epoch_ms - int(HISTORY.total_seconds() * 1000)

    @property
    def id_base_ms(self) -> int:
        return self._epoch_ms - int(ID_BASE_OFFSET.total_seconds() * 1000)

    def elapsed_s(self) -> float:
        return max(0.0, self._time.monotonic() - self._boot)

    def now_ms(self) -> int:
        return self._epoch_ms + int(self.elapsed_s() * 1000)

    def now(self) -> datetime:
        seconds, millis = divmod(self.now_ms(), 1000)
        return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=millis * 1000)

    def wall_now(self) -> datetime:
        return datetime.fromtimestamp(self._time.time(), tz=UTC)
