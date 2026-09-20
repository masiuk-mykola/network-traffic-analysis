import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI

from capture_api.domain.models import CasePatch, Severity
from capture_api.errors import DomainError
from capture_api.workspace.cases import SEEDED_OWNER, CaseStore
from capture_api.world.clock import TimeSource

log = logging.getLogger(__name__)

INTERVAL_S = 90.0
POLL_S = 1.0
MAX_CATCH_UP = 5
"""Edits applied at once after a long clock jump (a test advancing hours must not spam)."""

BOT_CASE_ID = "CASE-0002"

NOTES: tuple[str, ...] = (
    "Checked the branch firewall logs for the same window - nothing stands out yet.",
    "Asked the night shift whether anyone was uploading large archives.",
    "Re-ran the branch hunt with a wider window; the pattern is still there.",
    "Parked for today. Picking it back up with fresh eyes tomorrow.",
)

SUMMARIES: tuple[str, ...] = (
    "Outbound TLS from one branch workstation repeats on a fixed interval.",
    "Repeating branch beacon plus a burst of uploads; treating them as one story.",
)

SEVERITIES: tuple[Severity, ...] = ("medium", "high")


class TeammateBot:
    def __init__(
        self,
        cases: CaseStore,
        time_source: TimeSource,
        *,
        enabled: bool = True,
        interval_s: float = INTERVAL_S,
        case_id: str = BOT_CASE_ID,
        author_id: str = SEEDED_OWNER,
    ) -> None:
        self._cases = cases
        self._time = time_source
        self._enabled = enabled
        self._interval_s = interval_s
        self._case_id = case_id
        self._author_id = author_id
        self._step = 0
        self._edits = 0
        self._due = time_source.monotonic() + interval_s

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def case_id(self) -> str:
        return self._case_id

    @property
    def edits(self) -> int:
        return self._edits

    @property
    def interval_s(self) -> float:
        return self._interval_s

    def tick(self) -> int:
        applied = 0
        now = self._time.monotonic()
        while now >= self._due and applied < MAX_CATCH_UP:
            self.edit()
            self._due += self._interval_s
            applied += 1
        if now >= self._due:
            self._due = now + self._interval_s
        return applied

    def edit(self) -> None:
        step = self._step
        self._step += 1
        with suppress(DomainError):
            self._apply(step)
            self._edits += 1

    def _apply(self, step: int) -> None:
        kind = step % 3
        round_ = step // 3
        if kind == 0:
            self._cases.add_note(self._case_id, NOTES[round_ % len(NOTES)], self._author_id)
            return
        if kind == 1:
            summary = SUMMARIES[round_ % len(SUMMARIES)]
            self._cases.patch(self._case_id, CasePatch(summary=summary), "*")
            return
        current = self._cases.get(self._case_id).severity
        flipped = SEVERITIES[1] if current == SEVERITIES[0] else SEVERITIES[0]
        self._cases.patch(self._case_id, CasePatch(severity=flipped), "*")

    def reset(self) -> None:
        self._step = 0
        self._edits = 0
        self._due = self._time.monotonic() + self._interval_s

    def __len__(self) -> int:
        return self._edits


async def _run(bot: TeammateBot) -> None:
    while True:
        await asyncio.sleep(POLL_S)
        try:
            bot.tick()
        except Exception:  # pragma: no cover - the bot must never kill the server
            log.exception("teammate bot edit failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    settings = app.state.settings
    enabled = bool(settings.teammate_bot) and not bool(settings.full_history)
    bot = TeammateBot(app.state.cases, app.state.time, enabled=enabled)
    app.state.bot = bot
    task = asyncio.create_task(_run(bot)) if enabled else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
