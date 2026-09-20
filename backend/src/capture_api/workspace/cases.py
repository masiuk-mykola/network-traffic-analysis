import base64
import binascii
import hashlib
import hmac
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection

from capture_api.domain.base import from_epoch_ms
from capture_api.domain.models import (
    Case,
    CaseCreate,
    CasePatch,
    CaseSummary,
    EvidenceCreate,
    EvidencePin,
    Note,
)
from capture_api.errors import DomainError
from capture_api.workspace.hunts import check_if_match
from capture_api.world.clock import CaptureClock

DEFAULT_PAGE = 25
MAX_PAGE = 100
HOUR_MS = 3_600_000

SEEDED_OWNER = "sam"
"""Sam Okafor owns both seeded cases (and is the teammate bot's identity)."""


def encode_cursor(key: bytes, offset: int) -> str:
    payload = str(offset).encode()
    signature = hmac.new(key, payload, hashlib.sha256).digest()[:9]
    return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")


def decode_cursor(key: bytes, cursor: str) -> int:
    bad = DomainError(400, "invalid_cursor", "This cursor is not valid for /v1/cases.")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode())
    except (binascii.Error, ValueError) as exc:
        raise bad from exc
    payload, separator, signature = raw.rpartition(b".")
    if not separator:
        raise bad
    expected = hmac.new(key, payload, hashlib.sha256).digest()[:9]
    if not hmac.compare_digest(expected, signature):
        raise bad
    try:
        offset = int(payload)
    except ValueError as exc:
        raise bad from exc
    if offset < 0:
        raise bad
    return offset


def summarise(case: Case) -> CaseSummary:
    return CaseSummary(
        id=case.id,
        title=case.title,
        status=case.status,
        owner_id=case.owner_id,
        severity=case.severity,
        evidence_count=len(case.evidence),
        note_count=len(case.notes),
        created_at=case.created_at,
        updated_at=case.updated_at,
        version=case.version,
    )


class CaseStore:
    def __init__(self, clock: CaptureClock, cursor_key: bytes) -> None:
        self._clock = clock
        self._cursor_key = cursor_key
        self._cases: dict[str, Case] = {}
        self._counter = 0
        self._notes = 0
        self.reset()

    def _seed(self) -> None:
        epoch_ms = self._clock.epoch_ms
        first = self._make(
            case_id="CASE-0001",
            title="Port-scan noise from the IT scanner",
            status="closed",
            severity="low",
            summary=(
                "The recurring port-scan detections come from the scheduled IT asset scan. "
                "Confirmed benign and closed."
            ),
            created_ms=epoch_ms - 60 * HOUR_MS,
            updated_ms=epoch_ms - 52 * HOUR_MS,
            note="Scan window matches the IT change calendar; closing as expected behaviour.",
        )
        second = self._make(
            case_id="CASE-0002",
            title="Harbor branch anomalies",
            status="open",
            severity="medium",
            summary="Branch workstations show unusual outbound TLS. Investigating.",
            created_ms=epoch_ms - 20 * HOUR_MS,
            updated_ms=epoch_ms - 2 * HOUR_MS,
            note="Opened after the branch reported slow uploads during the night shift.",
        )
        self._cases = {first.id: first, second.id: second}
        self._counter = 2
        self._notes = 2

    def _make(
        self,
        *,
        case_id: str,
        title: str,
        status: Any,
        severity: Any,
        summary: str,
        created_ms: int,
        updated_ms: int,
        note: str,
    ) -> Case:
        index = int(case_id.rsplit("-", 1)[1])
        return Case(
            id=case_id,
            title=title,
            status=status,
            owner_id=SEEDED_OWNER,
            severity=severity,
            summary=summary,
            evidence=[],
            notes=[
                Note(
                    id=f"note_{index:04d}0001",
                    author_id=SEEDED_OWNER,
                    body=note,
                    created_at=from_epoch_ms(created_ms),
                )
            ],
            created_at=from_epoch_ms(created_ms),
            updated_at=from_epoch_ms(updated_ms),
            version=1,
        )

    def _now(self) -> datetime:
        return self._clock.now()

    def _bump(self, case: Case, **changes: Any) -> Case:
        updated = case.model_copy(
            update={**changes, "updated_at": self._now(), "version": case.version + 1}
        )
        self._cases[case.id] = updated
        return updated

    def _title_taken(self, title: str, *, exclude: str | None = None) -> bool:
        folded = title.strip().casefold()
        return any(
            case.id != exclude and case.title.casefold() == folded for case in self._cases.values()
        )

    def _ordered(self) -> list[Case]:
        cases = list(self._cases.values())
        cases.sort(key=lambda case: (case.created_at, case.id), reverse=True)
        return cases

    def get(self, case_id: str) -> Case:
        case = self._cases.get(case_id)
        if case is None:
            raise DomainError.not_found("case_not_found", f"No case '{case_id}'.")
        return case

    def page(self, cursor: str | None, limit: int | None) -> tuple[list[CaseSummary], str | None]:
        size = DEFAULT_PAGE if limit is None else max(1, min(MAX_PAGE, limit))
        offset = decode_cursor(self._cursor_key, cursor) if cursor else 0
        ordered = self._ordered()
        window = ordered[offset : offset + size]
        following = offset + len(window)
        next_cursor = (
            encode_cursor(self._cursor_key, following) if following < len(ordered) else None
        )
        return [summarise(case) for case in window], next_cursor

    def create(self, owner_id: str, body: CaseCreate) -> Case:
        if self._title_taken(body.title):
            raise DomainError(
                409,
                "title_taken",
                f"A case titled '{body.title}' already exists.",
                extra={"title": body.title},
            )
        self._counter += 1
        now = self._now()
        case = Case(
            id=f"CASE-{self._counter:04d}",
            title=body.title,
            status="open",
            owner_id=owner_id,
            severity=body.severity,
            summary=body.summary,
            evidence=[],
            notes=[],
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._cases[case.id] = case
        return case

    def patch(self, case_id: str, body: CasePatch, if_match: str | None) -> Case:
        case = self.get(case_id)
        check_if_match(
            if_match, case.version, current=case.model_dump(mode="json"), resource="case"
        )
        changes: dict[str, Any] = {}
        if "title" in body.model_fields_set and body.title is not None:
            if self._title_taken(body.title, exclude=case_id):
                raise DomainError(
                    409,
                    "title_taken",
                    f"A case titled '{body.title}' already exists.",
                    extra={"title": body.title},
                )
            changes["title"] = body.title
        for name in ("status", "severity", "owner_id"):
            value = getattr(body, name)
            if name in body.model_fields_set and value is not None:
                changes[name] = value
        if "summary" in body.model_fields_set:
            changes["summary"] = body.summary
        return self._bump(case, **changes)

    def pin(self, case_id: str, body: EvidenceCreate, user_id: str) -> tuple[Case, bool]:
        case = self.get(case_id)
        if any(pin.session_id == body.session_id for pin in case.evidence):
            return case, True
        pin = EvidencePin(
            session_id=body.session_id,
            stage=body.stage,
            note=body.note,
            pinned_by=user_id,
            pinned_at=self._now(),
        )
        return self._bump(case, evidence=[*case.evidence, pin]), False

    def unpin(self, case_id: str, session_id: str) -> Case:
        case = self.get(case_id)
        kept = [pin for pin in case.evidence if pin.session_id != session_id]
        if len(kept) == len(case.evidence):
            return case
        return self._bump(case, evidence=kept)

    def add_note(self, case_id: str, body: str, author_id: str) -> tuple[Case, Note]:
        case = self.get(case_id)
        self._notes += 1
        note = Note(
            id=f"note_{self._notes:08d}",
            author_id=author_id,
            body=body,
            created_at=self._now(),
        )
        return self._bump(case, notes=[*case.notes, note]), note

    def all(self) -> Sequence[Case]:
        return self._ordered()

    def reset(self) -> None:
        self._seed()

    def __len__(self) -> int:
        return len(self._cases)


def get_cases(conn: HTTPConnection) -> CaseStore:
    store = getattr(conn.app.state, "cases", None)
    if not isinstance(store, CaseStore):
        raise DomainError.unavailable("cases_unavailable", "The case store is not ready.", 5)
    return store


CasesDep = Annotated[CaseStore, Depends(get_cases)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    store = CaseStore(app.state.clock, app.state.settings.cursor_key)
    app.state.cases = store
    try:
        yield
    finally:
        store.reset()
