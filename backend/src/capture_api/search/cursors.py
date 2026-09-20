import base64
import hmac
from hashlib import sha256

from capture_api.domain.models import SortKey
from capture_api.errors import DomainError

SIGNATURE_BYTES = 16
SEPARATOR = "."


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(secret: bytes, payload: bytes) -> bytes:
    return hmac.new(secret, payload, sha256).digest()[:SIGNATURE_BYTES]


def invalid_cursor() -> DomainError:
    return DomainError(
        400,
        "invalid_cursor",
        "The cursor is not valid for this search; start again without one.",
    )


def sort_mismatch(cursor_sort: str, requested: str) -> DomainError:
    return DomainError(
        400,
        "cursor_sort_mismatch",
        f"The cursor was issued for sort '{cursor_sort}', not '{requested}'.",
        extra={"cursor_sort": cursor_sort, "sort": requested},
    )


def encode_cursor(secret: bytes, search_id: str, sort: SortKey, offset: int) -> str:
    payload = f"{search_id}|{sort}|{offset}".encode()
    return f"{_b64(payload)}{SEPARATOR}{_b64(_sign(secret, payload))}"


def decode_cursor(secret: bytes, cursor: str, search_id: str, sort: SortKey) -> int:
    body, separator, signature = cursor.partition(SEPARATOR)
    if not separator:
        raise invalid_cursor()
    try:
        payload = _unb64(body)
        expected = _unb64(signature)
    except (ValueError, UnicodeDecodeError) as exc:
        raise invalid_cursor() from exc
    if not hmac.compare_digest(_sign(secret, payload), expected):
        raise invalid_cursor()
    try:
        cursor_id, cursor_sort, raw_offset = payload.decode().split("|")
        offset = int(raw_offset)
    except (ValueError, UnicodeDecodeError) as exc:
        raise invalid_cursor() from exc
    if cursor_id != search_id or offset < 0:
        raise invalid_cursor()
    if cursor_sort != sort:
        raise sort_mismatch(cursor_sort, sort)
    return offset
