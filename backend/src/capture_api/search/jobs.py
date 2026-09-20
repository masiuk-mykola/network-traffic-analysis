import asyncio
import heapq
import logging
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from capture_api.domain.base import from_epoch_ms
from capture_api.domain.models import (
    FilterNode,
    Search,
    SearchProgress,
    SearchResults,
    SearchState,
    SearchStats,
    SearchWarning,
    SortKey,
)
from capture_api.errors import DomainError
from capture_api.search.compile import compile_for_world
from capture_api.search.cursors import decode_cursor, encode_cursor
from capture_api.search.estimate import total_rows, windows
from capture_api.settings import Settings
from capture_api.world.clock import FakeTimeSource, TimeSource
from capture_api.world.rng import Stream
from capture_api.world.types import Row, World

log = logging.getLogger(__name__)

SLOTS_PER_USER = 3
SLOT_RETRY_AFTER_S = 5
IDLE_TTL_S = 600.0
MAX_WINDOW_MS = 7 * 24 * 3_600 * 1_000
ROWS_PER_SECOND = 12_000
MIN_SCAN_S = 3.0
MAX_SCAN_S = 20.0
SCAN_STEPS = 40
DEFAULT_LIMIT = 200
MAX_LIMIT = 500
LIMIT_HEADER = "X-Limit-Applied"
SCAN_SORT: SortKey = "-ts"
REAP_INTERVAL_S = 30.0
MAX_REMEMBERED_EXPIRED = 512
SCAN_CPU_BUDGET_S = 60.0
FINISHED: frozenset[str] = frozenset({"done", "failed", "cancelled"})


class ScanFailed(Exception): ...


def scan_duration_s(total: int) -> float:
    return min(max(total / ROWS_PER_SECOND, MIN_SCAN_S), MAX_SCAN_S)


def bad_range(detail: str) -> DomainError:
    return DomainError(400, "bad_range", detail)


def validate_window(world: World, from_ms: int, to_ms: int, now_ms: int | None = None) -> None:
    if to_ms <= from_ms:
        raise bad_range("'to' must be after 'from'.")
    if to_ms - from_ms > MAX_WINDOW_MS:
        raise bad_range("The window may not be longer than 7 days.")
    now = world.capture_now_ms() if now_ms is None else now_ms
    if to_ms <= world.data_start_ms or from_ms > now:
        raise bad_range("The window does not overlap the captured period.")


def warnings_for(
    world: World, sensor_ids: Sequence[str], from_ms: int, to_ms: int
) -> tuple[SearchWarning, ...]:
    found: list[SearchWarning] = []
    for sensor_id in sensor_ids:
        for outage in world.outages(sensor_id):
            start = max(outage.start_ms, from_ms)
            end = min(outage.end_ms, to_ms)
            if end <= start:
                continue
            minutes = round((outage.end_ms - outage.start_ms) / 60_000)
            found.append(
                SearchWarning(
                    code="capture_gap",
                    sensor_id=sensor_id,
                    from_=from_epoch_ms(start),
                    to=from_epoch_ms(end),
                    detail=(
                        f"{sensor_id} captured nothing for about {minutes} minutes "
                        f"({outage.reason}); an absence of rows here is not an absence of "
                        "traffic."
                    ),
                )
            )
        sensor = world.sensor(sensor_id)
        if sensor is None or sensor.status != "lagging":
            continue
        visible = world.visible_until_ms(sensor_id)
        if to_ms > visible:
            found.append(
                SearchWarning(
                    code="sensor_lagging",
                    sensor_id=sensor_id,
                    from_=from_epoch_ms(visible),
                    to=from_epoch_ms(to_ms),
                    detail=(
                        f"{sensor_id} is {sensor.lag_s} s behind; the newest part of this "
                        "window has not arrived yet."
                    ),
                )
            )
    return tuple(found)


def _scan_key(row: Row) -> tuple[int, int]:
    return row.start_ms, row.id


def _sort_key(sort: SortKey) -> tuple[str, bool]:
    descending = sort.startswith("-")
    return sort.lstrip("-"), descending


def sorted_rows(rows: Sequence[Row], sort: SortKey) -> list[Row]:
    name, descending = _sort_key(sort)
    if name == "bytes":

        def key(row: Row) -> tuple[int, int]:
            return row.bytes_up + row.bytes_down, row.id
    elif name == "risk":

        def key(row: Row) -> tuple[int, int]:
            return row.risk_score, row.id
    else:

        def key(row: Row) -> tuple[int, int]:
            return row.start_ms, row.id

    return sorted(rows, key=key, reverse=descending)


@dataclass(slots=True)
class SearchJob:
    id: str
    user_id: str
    family_id: str
    sensor_ids: tuple[str, ...]
    from_ms: int
    to_ms: int
    filter_node: FilterNode
    sort: SortKey
    created_ms: int
    warnings: tuple[SearchWarning, ...] = ()
    state: SearchState = "queued"
    total: int = 0
    scanned: int = 0
    matched: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    finished_ms: int | None = None
    duration_s: float = 0.0
    fail_during_scan: bool = False
    rows: list[Row] = field(default_factory=list)
    touched: float = 0.0
    task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def finished(self) -> bool:
        return self.state in FINISHED

    @property
    def percent(self) -> float:
        if self.finished:
            return 100.0
        if self.total <= 0:
            return 0.0
        return round(min(100.0, self.scanned * 100.0 / self.total), 1)


def to_model(job: SearchJob) -> Search:
    return Search(
        id=job.id,
        state=job.state,
        sensor_ids=list(job.sensor_ids),
        from_=from_epoch_ms(job.from_ms),
        to=from_epoch_ms(job.to_ms),
        filter=job.filter_node,
        sort=job.sort,
        created_at=from_epoch_ms(job.created_ms),
        finished_at=None if job.finished_ms is None else from_epoch_ms(job.finished_ms),
        progress=SearchProgress(
            scanned_sessions=job.scanned,
            total_sessions_estimate=job.total,
            matched=job.matched,
            matched_is_estimate=job.state != "done",
            percent=job.percent,
        ),
        stats=SearchStats(matched_bytes_up=job.bytes_up, matched_bytes_down=job.bytes_down),
        warnings=list(job.warnings),
    )


@dataclass(frozen=True, slots=True)
class ResultPage:
    results: SearchResults
    limit_applied: int


class SearchService:
    def __init__(
        self,
        world: World,
        settings: Settings,
        time_source: TimeSource,
        *,
        paced: bool | None = None,
    ) -> None:
        self._world = world
        self._settings = settings
        self._time = time_source
        self._secret = settings.cursor_key
        self._jobs: dict[str, SearchJob] = {}
        self._expired: dict[str, str] = {}
        self._counter = 0
        self.paced = not isinstance(time_source, FakeTimeSource) if paced is None else paced
        """Whether the scan really waits between chunks (off on a fake clock)."""

    def _now_ms(self) -> int:
        return self._world.capture_now_ms()

    def _next_id(self) -> str:
        self._counter += 1
        return f"srch_{Stream(self._settings.seed, 'search', self._counter).hex(12)}"

    def _reap(self) -> None:
        now = self._time.monotonic()
        for job_id, job in list(self._jobs.items()):
            if now - job.touched < IDLE_TTL_S:
                continue
            self._abort(job)
            del self._jobs[job_id]
            self._remember_expired(job_id, job.user_id)

    def _remember_expired(self, job_id: str, user_id: str) -> None:
        self._expired[job_id] = user_id
        while len(self._expired) > MAX_REMEMBERED_EXPIRED:
            self._expired.pop(next(iter(self._expired)))

    def _abort(self, job: SearchJob) -> None:
        task = job.task
        job.task = None
        if task is not None and not task.done():
            task.cancel()
        if not job.finished:
            job.state = "cancelled"
            job.finished_ms = self._now_ms()

    def active_count(self) -> int:
        self._reap()
        return len(self._jobs)

    def reset(self) -> None:
        for job in list(self._jobs.values()):
            self._abort(job)
        self._jobs.clear()
        self._expired.clear()

    def create(
        self,
        *,
        user_id: str,
        family_id: str,
        sensor_ids: Sequence[str],
        from_ms: int,
        to_ms: int,
        filter_node: FilterNode,
        sort: SortKey = SCAN_SORT,
        fail_during_scan: bool = False,
    ) -> SearchJob:
        self._reap()
        active = [job for job in self._jobs.values() if job.user_id == user_id]
        if len(active) >= SLOTS_PER_USER:
            raise DomainError.rate_limited(
                "too_many_searches",
                (
                    f"You already hold {len(active)} searches; delete one "
                    "(DELETE /v1/searches/{id}) before starting another."
                ),
                SLOT_RETRY_AFTER_S,
                active=len(active),
            )
        job = SearchJob(
            id=self._next_id(),
            user_id=user_id,
            family_id=family_id,
            sensor_ids=tuple(sensor_ids),
            from_ms=from_ms,
            to_ms=to_ms,
            filter_node=filter_node,
            sort=sort,
            created_ms=self._now_ms(),
            warnings=warnings_for(self._world, sensor_ids, from_ms, to_ms),
            fail_during_scan=fail_during_scan,
            touched=self._time.monotonic(),
        )
        self._jobs[job.id] = job
        self._start(job)
        return job

    def _start(self, job: SearchJob) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            log.debug("no running loop; %s stays queued until run() is awaited", job.id)
            return
        job.task = asyncio.create_task(self.run(job), name=job.id)

    def peek(self, search_id: str) -> SearchJob | None:
        return self._jobs.get(search_id)

    def get(self, search_id: str, user_id: str) -> SearchJob:
        self._reap()
        job = self._jobs.get(search_id)
        if job is None or job.user_id != user_id:
            if self._expired.get(search_id) == user_id:
                raise DomainError(
                    410,
                    "search_expired",
                    "This search was idle for more than 10 minutes and has been discarded.",
                )
            raise DomainError.not_found("search_not_found", f"No search '{search_id}'.")
        job.touched = self._time.monotonic()
        return job

    def cancel(self, search_id: str, user_id: str) -> None:
        self._reap()
        job = self._jobs.get(search_id)
        if job is None or job.user_id != user_id:
            return
        self._abort(job)
        del self._jobs[search_id]
        self._expired.pop(search_id, None)

    def results(
        self,
        job: SearchJob,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        sort: SortKey | None = None,
    ) -> ResultPage:
        applied = max(1, min(DEFAULT_LIMIT if limit is None else limit, MAX_LIMIT))
        order: SortKey = sort or job.sort
        if order != SCAN_SORT and job.state != "done":
            raise DomainError(
                409,
                "search_running",
                (
                    f"Sorting by '{order}' needs the whole result set; the search is "
                    f"{job.state}. Read the default '-ts' order, or wait for state 'done'."
                ),
            )
        offset = 0 if cursor is None else decode_cursor(self._secret, cursor, job.id, order)
        rows = job.rows if order == SCAN_SORT else sorted_rows(job.rows, order)
        page = rows[offset : offset + applied]
        end = offset + len(page)
        more = end < len(rows)
        return ResultPage(
            results=SearchResults(
                items=[self._world.to_session_row(row) for row in page],
                next_cursor=encode_cursor(self._secret, job.id, order, end) if more else None,
                complete=job.finished and not more,
                matched_so_far=job.matched,
            ),
            limit_applied=applied,
        )

    def matched_rows(self, job: SearchJob) -> tuple[Row, ...]:
        return tuple(job.rows)

    async def run(self, job: SearchJob) -> None:
        job.state = "running"
        try:
            await self._scan(job)
        except asyncio.CancelledError:
            job.state = "cancelled"
            job.finished_ms = self._now_ms()
            raise
        except ScanFailed as exc:
            log.info("search %s failed: %s", job.id, exc)
            job.state = "failed"
            job.finished_ms = self._now_ms()
        except Exception:
            log.exception("search %s crashed", job.id)
            job.state = "failed"
            job.finished_ms = self._now_ms()
        else:
            job.state = "done"
            job.finished_ms = self._now_ms()
            job.total = max(job.total, job.scanned)

    async def _scan(self, job: SearchJob) -> None:
        world = self._world
        resolved = windows(world, job.sensor_ids, job.from_ms, job.to_ms)
        job.total = total_rows(world, resolved)
        job.duration_s = scan_duration_s(job.total)
        predicate = compile_for_world(job.filter_node, world)
        chunk = max(1, job.total // SCAN_STEPS)
        delay = job.duration_s / SCAN_STEPS
        fail_at = job.total // 2 if job.fail_during_scan else None
        deadline = asyncio.get_running_loop().time() + SCAN_CPU_BUDGET_S
        for row in self._rows_newest_first(resolved):
            job.scanned += 1
            if predicate(row):
                job.matched += 1
                job.rows.append(row)
                job.bytes_up += row.bytes_up
                job.bytes_down += row.bytes_down
            if fail_at is not None and job.scanned >= fail_at:
                raise ScanFailed(f"the index gave up after {job.scanned} sessions")
            if job.scanned % chunk == 0:
                if asyncio.get_running_loop().time() > deadline:
                    raise ScanFailed(
                        f"the scan exceeded its {SCAN_CPU_BUDGET_S:.0f} second budget after "
                        f"{job.scanned} sessions; simplify the filter"
                    )
                await self._pause(delay)
        await self._pause(delay)

    def _rows_newest_first(self, resolved: Sequence[tuple[str, int, int]]) -> Iterable[Row]:
        streams = [
            self._world.rows_desc(sensor_id, start, end) for sensor_id, start, end in resolved
        ]
        if len(streams) == 1:
            return streams[0]
        return heapq.merge(*streams, key=_scan_key, reverse=True)

    async def _pause(self, delay: float) -> None:
        await asyncio.sleep(delay if self.paced else 0)

    async def run_reaper(self, interval_s: float = REAP_INTERVAL_S) -> None:
        while True:
            await asyncio.sleep(interval_s)
            self._reap()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    service = SearchService(app.state.world, app.state.settings, app.state.time)
    app.state.searches = service
    reaper: asyncio.Task[Any] = asyncio.create_task(service.run_reaper(), name="search-reaper")
    try:
        yield
    finally:
        reaper.cancel()
        with suppress(asyncio.CancelledError):
            await reaper
        service.reset()
