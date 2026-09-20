import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from capture_api.errors import DomainError
from capture_api.platform.permissions import User, normalize_email
from capture_api.world.clock import TimeSource

ACCESS_PREFIX = "at_"
REFRESH_PREFIX = "rt_"
ACCESS_RANDOM_CHARS = 32
REFRESH_RANDOM_CHARS = 40

type AccessState = Literal["ok", "token_expired", "invalid_token", "session_revoked"]
type RevokeReason = Literal["logout", "refresh_reused", "admin", "reset"]
type RevocationCallback = Callable[[str, RevokeReason], None]

log = logging.getLogger(__name__)

_ACCESS_DETAIL: dict[str, str] = {
    "token_expired": "The access token has expired; refresh it and replay the request.",
    "invalid_token": "Missing, malformed or unknown access token.",
    "session_revoked": "This session was revoked; sign in again.",
}


def _random_token(prefix: str, chars: int) -> str:
    raw = secrets.token_urlsafe(chars)
    while len(raw) < chars:  # pragma: no cover - token_urlsafe(n) yields >= n chars
        raw += secrets.token_urlsafe(chars)
    return prefix + raw[:chars]


def _well_formed(token: str, prefix: str, chars: int) -> bool:
    return len(token) == len(prefix) + chars and token.startswith(prefix)


@dataclass(slots=True)
class TokenFamily:
    family_id: str
    user: User
    created: float
    refresh_last_used: float
    refresh_token: str
    access_token: str
    access_exp: float
    rotations: int = 0
    revoked: bool = False
    revoked_reason: RevokeReason | None = None
    revoked_at: float | None = None
    access_tokens: list[str] = field(default_factory=list)
    refresh_tokens: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _AccessRecord:
    family_id: str
    exp: float


@dataclass(slots=True)
class _RefreshRecord:
    family_id: str
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    family_id: str
    user: User
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_in: int


@dataclass(frozen=True, slots=True)
class AccessGrant:
    family_id: str
    user: User
    token: str
    expires_at: float
    """Monotonic seconds; may move earlier if an admin expires tokens."""


class TokenStore:
    def __init__(
        self,
        *,
        seed: str,
        time_source: TimeSource,
        access_ttl: Callable[[], float],
        refresh_idle_s: float,
        refresh_max_s: float,
    ) -> None:
        self._seed = seed
        self._time = time_source
        self.access_ttl: Callable[[], float] = access_ttl
        """Current access TTL in seconds; the chaos controller may replace this provider."""
        self._refresh_idle_s = refresh_idle_s
        self._refresh_max_s = refresh_max_s
        self._families: dict[str, TokenFamily] = {}
        self._access: dict[str, _AccessRecord] = {}
        self._refresh: dict[str, _RefreshRecord] = {}
        self._counter = 0
        self._family_callbacks: dict[str, list[RevocationCallback]] = {}
        self._listeners: list[RevocationCallback] = []

    def _now(self) -> float:
        return self._time.monotonic()

    def _next_family_id(self) -> str:
        self._counter += 1
        digest = hashlib.blake2b(
            f"{self._seed}|family|{self._counter}".encode(), digest_size=6
        ).hexdigest()
        return f"fam_{digest}"

    def _refresh_expires_in(self, family: TokenFamily, now: float) -> int:
        idle_left = family.refresh_last_used + self._refresh_idle_s - now
        max_left = family.created + self._refresh_max_s - now
        return max(0, int(min(idle_left, max_left)))

    def _mint(self, family: TokenFamily, now: float) -> IssuedTokens:
        ttl = float(self.access_ttl())
        access = _random_token(ACCESS_PREFIX, ACCESS_RANDOM_CHARS)
        refresh = _random_token(REFRESH_PREFIX, REFRESH_RANDOM_CHARS)
        self._access[access] = _AccessRecord(family.family_id, now + ttl)
        self._refresh[refresh] = _RefreshRecord(family.family_id)
        family.access_tokens.append(access)
        family.refresh_tokens.append(refresh)
        family.access_token = access
        family.access_exp = now + ttl
        family.refresh_token = refresh
        family.refresh_last_used = now
        return IssuedTokens(
            family_id=family.family_id,
            user=family.user,
            access_token=access,
            access_expires_in=int(ttl),
            refresh_token=refresh,
            refresh_expires_in=self._refresh_expires_in(family, now),
        )

    def login(self, user: User) -> IssuedTokens:
        self.sweep()
        now = self._now()
        family = TokenFamily(
            family_id=self._next_family_id(),
            user=user,
            created=now,
            refresh_last_used=now,
            refresh_token="",
            access_token="",
            access_exp=now,
        )
        self._families[family.family_id] = family
        return self._mint(family, now)

    def refresh(self, refresh_token: str) -> IssuedTokens:
        record = (
            self._refresh.get(refresh_token)
            if _well_formed(refresh_token, REFRESH_PREFIX, REFRESH_RANDOM_CHARS)
            else None
        )
        family = self._families.get(record.family_id) if record else None
        if record is None or family is None:
            raise DomainError(401, "refresh_invalid", "Unknown or malformed refresh token.")
        if family.revoked:
            raise DomainError(401, "session_revoked", _ACCESS_DETAIL["session_revoked"])
        if record.consumed:
            self.revoke_family(family.family_id, "refresh_reused")
            raise DomainError(
                401,
                "refresh_reused",
                "This refresh token was already used; the whole session has been revoked.",
            )
        now = self._now()
        idle = now - family.refresh_last_used > self._refresh_idle_s
        too_old = now - family.created > self._refresh_max_s
        if idle or too_old:
            record.consumed = True
            raise DomainError(401, "refresh_expired", "The refresh token has expired.")
        record.consumed = True
        family.rotations += 1
        return self._mint(family, now)

    def logout(self, access_token: str) -> str:
        record = self._access.get(access_token)
        if record is None or record.family_id not in self._families:
            raise DomainError.unauthorized("invalid_token", _ACCESS_DETAIL["invalid_token"])
        self.revoke_family(record.family_id, "logout")
        return record.family_id

    def access_status(self, access_token: str) -> AccessState:
        record = self._access.get(access_token)
        family = self._families.get(record.family_id) if record else None
        if record is None or family is None:
            return "invalid_token"
        if family.revoked:
            return "session_revoked"
        if self._now() >= record.exp:
            return "token_expired"
        return "ok"

    def authenticate(self, access_token: str | None) -> AccessGrant:
        state: AccessState = (
            self.access_status(access_token) if access_token is not None else "invalid_token"
        )
        if state != "ok" or access_token is None:
            raise DomainError.unauthorized(state, _ACCESS_DETAIL[state])
        record = self._access[access_token]
        family = self._families[record.family_id]
        return AccessGrant(
            family_id=family.family_id,
            user=family.user,
            token=access_token,
            expires_at=record.exp,
        )

    def access_remaining_s(self, access_token: str) -> float | None:
        record = self._access.get(access_token)
        return None if record is None else record.exp - self._now()

    def revoke_family(self, family_id: str, reason: RevokeReason) -> bool:
        family = self._families.get(family_id)
        if family is None or family.revoked:
            return False
        family.revoked = True
        family.revoked_reason = reason
        family.revoked_at = self._now()
        callbacks = [*self._family_callbacks.pop(family_id, []), *self._listeners]
        for callback in callbacks:
            try:
                callback(family_id, reason)
            except Exception:
                log.exception("revocation callback failed for %s", family_id)
        return True

    def on_family_revoked(self, family_id: str, callback: RevocationCallback) -> Callable[[], None]:
        family = self._families.get(family_id)
        if family is None or family.revoked:
            callback(
                family_id, family.revoked_reason if family and family.revoked_reason else "reset"
            )
            return lambda: None
        self._family_callbacks.setdefault(family_id, []).append(callback)

        def unsubscribe() -> None:
            callbacks = self._family_callbacks.get(family_id)
            if callbacks and callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    def add_revocation_listener(self, callback: RevocationCallback) -> Callable[[], None]:
        self._listeners.append(callback)

        def remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return remove

    def expire_access_tokens(self, email: str | None = None) -> int:
        now = self._now()
        wanted = normalize_email(email) if email else None
        count = 0
        for record in self._access.values():
            family = self._families.get(record.family_id)
            if family is None or family.revoked or record.exp <= now:
                continue
            if wanted is None or family.user.email == wanted:
                record.exp = now
                count += 1
        return count

    def revoke_user(self, email: str) -> int:
        wanted = normalize_email(email)
        targets = [
            f.family_id for f in self._families.values() if f.user.email == wanted and not f.revoked
        ]
        return sum(1 for fid in targets if self.revoke_family(fid, "admin"))

    def reset(self) -> None:
        for family_id in list(self._families):
            self.revoke_family(family_id, "reset")
        self._families.clear()
        self._access.clear()
        self._refresh.clear()
        self._family_callbacks.clear()
        self._counter = 0

    def sweep(self) -> int:
        now = self._now()
        horizon = self._refresh_max_s + float(self.access_ttl())
        stale = [f for f in self._families.values() if now - f.created > horizon]
        for family in stale:
            self.revoke_family(family.family_id, "reset")
            for token in family.access_tokens:
                self._access.pop(token, None)
            for token in family.refresh_tokens:
                self._refresh.pop(token, None)
            self._families.pop(family.family_id, None)
            self._family_callbacks.pop(family.family_id, None)
        return len(stale)

    def family(self, family_id: str) -> TokenFamily | None:
        return self._families.get(family_id)

    def family_count(self, *, active_only: bool = True) -> int:
        return sum(1 for f in self._families.values() if not (active_only and f.revoked))
