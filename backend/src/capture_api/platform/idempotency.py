import hashlib
import json
import re
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection

from capture_api.errors import DomainError
from capture_api.world.clock import TimeSource

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
TTL_S = 600.0
REPLAY_HEADER = "Idempotent-Replayed"
MAX_ENTRIES = 4096


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    scope: str
    family_id: str
    key: str
    fingerprint: str
    value: Any
    """Whatever the route needs to replay — typically the created resource's id."""
    created: float


class IdempotencyStore:
    def __init__(self, time_source: TimeSource, *, ttl_s: float = TTL_S) -> None:
        self._time = time_source
        self._ttl_s = ttl_s
        self._records: dict[tuple[str, str, str], IdempotencyRecord] = {}

    @staticmethod
    def validate_key(raw: str | None) -> str | None:
        if raw is None:
            return None
        key = raw.strip()
        if not KEY_PATTERN.match(key):
            raise DomainError(
                422,
                "invalid_idempotency_key",
                "Idempotency-Key must be 8-64 characters of [A-Za-z0-9_-].",
            )
        return key

    @staticmethod
    def fingerprint(body: bytes | str | Mapping[str, Any] | None) -> str:
        if body is None:
            return hashlib.sha256(b"").hexdigest()
        if isinstance(body, Mapping):
            payload: Any = body
        else:
            raw = body.encode() if isinstance(body, str) else body
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return hashlib.sha256(raw).hexdigest()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _purge(self, now: float) -> None:
        stale = [k for k, r in self._records.items() if now - r.created >= self._ttl_s]
        for key in stale:
            del self._records[key]
        if len(self._records) > MAX_ENTRIES:
            oldest = sorted(self._records.items(), key=lambda item: item[1].created)
            for key, _ in oldest[: len(self._records) - MAX_ENTRIES]:
                del self._records[key]

    def lookup(
        self, scope: str, family_id: str, key: str, fingerprint: str
    ) -> IdempotencyRecord | None:
        now = self._time.monotonic()
        self._purge(now)
        record = self._records.get((scope, family_id, key))
        if record is None:
            return None
        if record.fingerprint != fingerprint:
            raise DomainError(
                422,
                "idempotency_key_mismatch",
                "This Idempotency-Key was already used with a different request body.",
            )
        return record

    def remember(
        self, scope: str, family_id: str, key: str, fingerprint: str, value: Any
    ) -> IdempotencyRecord:
        now = self._time.monotonic()
        self._purge(now)
        record = IdempotencyRecord(
            scope=scope,
            family_id=family_id,
            key=key,
            fingerprint=fingerprint,
            value=value,
            created=now,
        )
        self._records[(scope, family_id, key)] = record
        return record

    def forget(self, scope: str, family_id: str, key: str) -> None:
        self._records.pop((scope, family_id, key), None)

    def reset(self) -> None:
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)


def get_idempotency(conn: HTTPConnection) -> IdempotencyStore:
    return cast(IdempotencyStore, conn.app.state.idempotency)


IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    app.state.idempotency = IdempotencyStore(app.state.time)
    try:
        yield
    finally:
        app.state.idempotency.reset()
