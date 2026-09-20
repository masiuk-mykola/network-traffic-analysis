from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from capture_api.domain.models import Permission, Profile, Role

ROLE_PERMISSIONS: Mapping[Role, tuple[Permission, ...]] = {
    "analyst": (
        "sessions:read",
        "pcap:download",
        "files:download",
        "hunts:write",
        "cases:write",
        "imports:create",
        "live:read",
    ),
    "observer": ("sessions:read", "live:read"),
}

ROLE_DENIED_SENSORS: Mapping[Role, frozenset[str]] = {
    "analyst": frozenset(),
    "observer": frozenset({"dc-east"}),
}
"""Sensors a role may never read. Every other sensor, imports included, is readable."""


@dataclass(frozen=True, slots=True)
class User:
    id: str
    email: str
    password: str
    role: Role
    display_name: str

    @property
    def permissions(self) -> tuple[Permission, ...]:
        return ROLE_PERMISSIONS[self.role]


USERS: tuple[User, ...] = (
    User("ana", "ana@quillmere.example", "demo-analyst", "analyst", "Ana Duarte"),
    User("oli", "oli@quillmere.example", "demo-observer", "observer", "Oliver Brandt"),
    User("sam", "sam@quillmere.example", "demo-teammate", "analyst", "Sam Okafor"),
)
"""``sam`` is also the teammate bot's identity."""

_BY_EMAIL: Mapping[str, User] = {u.email: u for u in USERS}
_BY_ID: Mapping[str, User] = {u.id: u for u in USERS}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_by_email(email: str) -> User | None:
    return _BY_EMAIL.get(normalize_email(email))


def user_by_id(user_id: str) -> User | None:
    return _BY_ID.get(user_id)


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def can_read_sensor(role: Role, sensor_id: str) -> bool:
    return sensor_id not in ROLE_DENIED_SENSORS[role]


def readable_sensor_ids(role: Role, sensor_ids: Iterable[str]) -> list[str]:
    return [s for s in sensor_ids if can_read_sensor(role, s)]


def build_profile(user: User, known_sensor_ids: Iterable[str]) -> Profile:
    return Profile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        permissions=list(user.permissions),
        sensor_ids=readable_sensor_ids(user.role, known_sensor_ids),
    )
