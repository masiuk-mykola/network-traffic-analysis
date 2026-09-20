import hashlib
from functools import lru_cache

from capture_api.world.ids import parse_session_id
from capture_api.world.rng import Stream
from capture_api.world.types import FileData, FileSpec, Row

MAGIC: dict[str, bytes] = {
    "application/vnd.ms-excel.sheet.macroEnabled.12": b"PK\x03\x04\x14\x00\x06\x00",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04\x14\x00",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/zip": b"PK\x03\x04",
    "application/pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n",
    "application/msword": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",
    "image/gif": b"GIF89a",
    "application/gzip": b"\x1f\x8b\x08\x00",
}

_TEXT_ALPHABET = b"abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:-\n"


def file_id(session_id: int, ordinal: int) -> str:
    return f"f{session_id}-{ordinal}"


def parse_file_id(text: str) -> tuple[int, int] | None:
    if not text.startswith("f") or "-" not in text:
        return None
    session_part, _, ordinal_part = text[1:].partition("-")
    session_id = parse_session_id(session_part)
    if session_id is None or not ordinal_part.isdigit() or len(ordinal_part) > 3:
        return None
    if ordinal_part != str(int(ordinal_part)):
        return None
    return session_id, int(ordinal_part)


def file_bytes(seed: str, fid: str, mime: str, size: int) -> bytes:
    stream = Stream(seed, "file", fid)
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        raw = stream.bytes(size)
        return bytes(_TEXT_ALPHABET[b % len(_TEXT_ALPHABET)] for b in raw)
    magic = MAGIC.get(mime, b"")[:size]
    return magic + stream.bytes(size - len(magic))


@lru_cache(maxsize=8192)
def file_sha256(seed: str, fid: str, mime: str, size: int) -> str:
    return hashlib.sha256(file_bytes(seed, fid, mime, size)).hexdigest()


def carve(seed: str, session_id: int, ordinal: int, spec: FileSpec) -> FileData:
    fid = file_id(session_id, ordinal)
    return FileData(
        id=fid,
        session_id=session_id,
        name=spec.name,
        mime=spec.mime,
        size=spec.size,
        sha256=file_sha256(seed, fid, spec.mime, spec.size),
        source=spec.source,
        purged=spec.purged,
        trap=spec.trap,
    )


def carve_files(seed: str, row: Row) -> tuple[FileData, ...]:
    return tuple(carve(seed, row.id, i, spec) for i, spec in enumerate(row.files))
