import hashlib
import re
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection

from capture_api.domain.models import Hunt, HuntCreate, HuntPatch
from capture_api.errors import DomainError
from capture_api.world.clock import CaptureClock

ETAG_RE = re.compile(r'^(?:W/)?"?v(\d+)"?$')
"""``"v3"``, ``W/"v3"`` and the bare ``v3`` all name version 3."""


def etag(version: int) -> str:
    return f'"v{version}"'


def matches_etag(raw: str, version: int) -> bool:
    for candidate in raw.split(","):
        tag = candidate.strip()
        if not tag:
            continue
        if tag == "*":
            return True
        found = ETAG_RE.match(tag)
        if found is not None and int(found.group(1)) == version:
            return True
    return False


def check_if_match(
    raw: str | None,
    version: int,
    *,
    current: Mapping[str, Any],
    resource: str,
    required: bool = True,
) -> None:
    header = {"ETag": etag(version)}
    if raw is None or not raw.strip():
        if not required:
            return
        raise DomainError(
            428,
            "precondition_required",
            f"Send If-Match with the {resource}'s current ETag to update it.",
            headers=header,
        )
    if not matches_etag(raw, version):
        raise DomainError(
            412,
            "etag_mismatch",
            f"This {resource} changed since you read it; reload and re-apply your edit.",
            extra={"current": dict(current)},
            headers=header,
        )


class HuntStore:
    def __init__(self, clock: CaptureClock, seed: str) -> None:
        self._clock = clock
        self._seed = seed
        self._hunts: dict[str, Hunt] = {}
        self._counter = 0

    def _new_id(self) -> str:
        self._counter += 1
        digest = hashlib.blake2b(
            f"{self._seed}|hunt|{self._counter}".encode(), digest_size=6
        ).hexdigest()
        return f"hnt_{digest}"

    def _name_taken(self, owner_id: str, name: str, *, exclude: str | None = None) -> bool:
        folded = name.strip().casefold()
        return any(
            hunt.owner_id == owner_id and hunt.id != exclude and hunt.name.casefold() == folded
            for hunt in self._hunts.values()
        )

    def _owned(self, owner_id: str, hunt_id: str) -> Hunt:
        hunt = self._hunts.get(hunt_id)
        if hunt is None or hunt.owner_id != owner_id:
            raise DomainError.not_found("hunt_not_found", f"No hunt '{hunt_id}'.")
        return hunt

    @staticmethod
    def _conflict(name: str) -> DomainError:
        return DomainError(
            409,
            "name_taken",
            f"You already have a hunt named '{name}'.",
            extra={"name": name},
        )

    def list(self, owner_id: str) -> list[Hunt]:
        own = [hunt for hunt in self._hunts.values() if hunt.owner_id == owner_id]
        own.sort(key=lambda hunt: (hunt.created_at, hunt.id), reverse=True)
        return own

    def get(self, owner_id: str, hunt_id: str) -> Hunt:
        return self._owned(owner_id, hunt_id)

    def create(self, owner_id: str, body: HuntCreate) -> Hunt:
        if self._name_taken(owner_id, body.name):
            raise self._conflict(body.name)
        now = self._clock.now()
        hunt = Hunt(
            id=self._new_id(),
            owner_id=owner_id,
            name=body.name,
            description=body.description,
            query=body.query,
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._hunts[hunt.id] = hunt
        return hunt

    def patch(self, owner_id: str, hunt_id: str, body: HuntPatch, if_match: str | None) -> Hunt:
        hunt = self._owned(owner_id, hunt_id)
        check_if_match(
            if_match,
            hunt.version,
            current=hunt.model_dump(mode="json"),
            resource="hunt",
        )
        changes: dict[str, Any] = {}
        if "name" in body.model_fields_set and body.name is not None:
            if self._name_taken(owner_id, body.name, exclude=hunt_id):
                raise self._conflict(body.name)
            changes["name"] = body.name
        if "description" in body.model_fields_set:
            changes["description"] = body.description
        if "query" in body.model_fields_set and body.query is not None:
            changes["query"] = body.query
        updated = hunt.model_copy(
            update={**changes, "updated_at": self._clock.now(), "version": hunt.version + 1}
        )
        self._hunts[hunt_id] = updated
        return updated

    def delete(self, owner_id: str, hunt_id: str, if_match: str | None) -> None:
        hunt = self._owned(owner_id, hunt_id)
        check_if_match(
            if_match,
            hunt.version,
            current=hunt.model_dump(mode="json"),
            resource="hunt",
            required=False,
        )
        del self._hunts[hunt_id]

    def touch(self, hunt_id: str) -> int | None:
        hunt = self._hunts.get(hunt_id)
        if hunt is None:
            return None
        updated = hunt.model_copy(
            update={"version": hunt.version + 1, "updated_at": self._clock.now()}
        )
        self._hunts[hunt_id] = updated
        return updated.version

    def all(self) -> Sequence[Hunt]:
        return list(self._hunts.values())

    def reset(self) -> None:
        self._hunts.clear()
        self._counter = 0

    def __len__(self) -> int:
        return len(self._hunts)


def get_hunts(conn: HTTPConnection) -> HuntStore:
    store = getattr(conn.app.state, "hunts", None)
    if not isinstance(store, HuntStore):
        raise DomainError.unavailable("hunts_unavailable", "The hunt store is not ready.", 5)
    return store


HuntsDep = Annotated[HuntStore, Depends(get_hunts)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    store = HuntStore(app.state.clock, app.state.settings.seed)
    app.state.hunts = store
    try:
        yield
    finally:
        store.reset()
