SENSOR_SHIFT = 56
MINUTE_SHIFT = 20
MAX_SENSOR_INDEX = (1 << 8) - 1
MAX_MINUTE_INDEX = (1 << (SENSOR_SHIFT - MINUTE_SHIFT)) - 1
MAX_ORDINAL = (1 << MINUTE_SHIFT) - 1
MAX_ID = (1 << 64) - 1
MINUTE_MS = 60_000


def minute_index(ts_ms: int, id_base_ms: int) -> int:
    return (ts_ms - id_base_ms) // MINUTE_MS


def minute_start_ms(index: int, id_base_ms: int) -> int:
    return id_base_ms + index * MINUTE_MS


def encode_session_id(sensor_index: int, minute: int, ordinal: int) -> int:
    if not 1 <= sensor_index <= MAX_SENSOR_INDEX:
        raise ValueError(f"sensor_index {sensor_index} out of range")
    if not 0 <= minute <= MAX_MINUTE_INDEX:
        raise ValueError(f"minute_index {minute} out of range")
    if not 0 <= ordinal <= MAX_ORDINAL:
        raise ValueError(f"ordinal {ordinal} out of range")
    return (sensor_index << SENSOR_SHIFT) | (minute << MINUTE_SHIFT) | ordinal


def decode_session_id(session_id: int) -> tuple[int, int, int]:
    return (
        session_id >> SENSOR_SHIFT,
        (session_id >> MINUTE_SHIFT) & MAX_MINUTE_INDEX,
        session_id & MAX_ORDINAL,
    )


def parse_session_id(text: str) -> int | None:
    if not text or len(text) > 20 or not text.isascii() or not text.isdigit():
        return None
    if text[0] == "0":
        return None
    value = int(text)
    if value > MAX_ID or value >> SENSOR_SHIFT == 0:
        return None
    return value
