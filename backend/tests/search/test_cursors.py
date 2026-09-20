import pytest

from capture_api.errors import DomainError
from capture_api.search.cursors import decode_cursor, encode_cursor

SECRET = b"a-cursor-secret"


def test_round_trips_an_offset() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 400)
    assert decode_cursor(SECRET, cursor, "srch_1", "-ts") == 400


def test_is_opaque() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 400)
    assert "srch_1" not in cursor
    assert "400" not in cursor


def test_a_tampered_cursor_is_invalid() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 400)
    payload, _, signature = cursor.partition(".")
    tampered = f"{payload}x.{signature}"
    with pytest.raises(DomainError) as caught:
        decode_cursor(SECRET, tampered, "srch_1", "-ts")
    assert caught.value.status == 400
    assert caught.value.code == "invalid_cursor"


@pytest.mark.parametrize("cursor", ["", "nonsense", "a.b", "!!!.???"])
def test_garbage_is_invalid(cursor: str) -> None:
    with pytest.raises(DomainError) as caught:
        decode_cursor(SECRET, cursor, "srch_1", "-ts")
    assert caught.value.code == "invalid_cursor"


def test_another_secret_does_not_verify() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 5)
    with pytest.raises(DomainError) as caught:
        decode_cursor(b"other", cursor, "srch_1", "-ts")
    assert caught.value.code == "invalid_cursor"


def test_a_cursor_of_another_search_is_invalid() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 5)
    with pytest.raises(DomainError) as caught:
        decode_cursor(SECRET, cursor, "srch_2", "-ts")
    assert caught.value.code == "invalid_cursor"


def test_a_cursor_of_another_sort_is_a_sort_mismatch() -> None:
    cursor = encode_cursor(SECRET, "srch_1", "-ts", 5)
    with pytest.raises(DomainError) as caught:
        decode_cursor(SECRET, cursor, "srch_1", "-bytes")
    assert caught.value.status == 400
    assert caught.value.code == "cursor_sort_mismatch"
    assert caught.value.extra["cursor_sort"] == "-ts"
