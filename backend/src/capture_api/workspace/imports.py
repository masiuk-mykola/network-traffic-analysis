import asyncio
import hashlib
import struct
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import Depends, FastAPI
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header
from starlette.requests import HTTPConnection, Request

from capture_api.domain.models import Import, ImportState
from capture_api.errors import DomainError
from capture_api.world.clock import CaptureClock, TimeSource
from capture_api.world.types import World

if TYPE_CHECKING:
    from python_multipart.multipart import MultipartCallbacks

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
READ_RATE_BPS = 8 * 1024 * 1024
MAX_META_BYTES = 64 * 1024
MAX_RECORD_BYTES = 16 * 1024 * 1024
SESSION_BYTES = 4096
MAX_IMPORT_SESSIONS = 5_000
HOUR_MS = 3_600_000

MIN_INDEX_S = 5.0
MAX_INDEX_S = 10.0
POLL_S = 0.25

PCAP_MAGICS: Mapping[bytes, tuple[str, str, int]] = {
    b"\xa1\xb2\xc3\xd4": ("pcap", ">", 1_000),
    b"\xd4\xc3\xb2\xa1": ("pcap", "<", 1_000),
    b"\xa1\xb2\x3c\x4d": ("pcap", ">", 1_000_000),
    b"\x4d\x3c\xb2\xa1": ("pcap", "<", 1_000_000),
    b"\x0a\x0d\x0d\x0a": ("pcapng", "<", 0),
}
"""Magic → (kind, endianness, divisor turning the fractional field into milliseconds)."""


def not_a_capture() -> DomainError:
    return DomainError(
        415,
        "not_a_capture",
        "The uploaded file is not a pcap or pcapng capture (unexpected magic bytes).",
    )


def too_large() -> DomainError:
    return DomainError(
        413,
        "too_large",
        "Captures larger than 100 MB cannot be imported.",
        extra={"limit_bytes": MAX_UPLOAD_BYTES},
    )


class CaptureScanner:
    def __init__(self) -> None:
        self._sha = hashlib.sha256()
        self._buffer = bytearray()
        self._state = "magic"
        self._endian = "<"
        self._divisor = 1_000
        self._skip = 0
        self.size = 0
        self.kind: str | None = None
        self.magic_decided = False
        self.first_ts_ms: int | None = None
        self.last_ts_ms: int | None = None

    def feed(self, chunk: bytes) -> None:
        self._sha.update(chunk)
        self.size += len(chunk)
        if self._state == "done":
            return
        self._buffer += chunk
        self._parse()

    def hexdigest(self) -> str:
        return self._sha.hexdigest()

    @property
    def is_capture(self) -> bool:
        return self.kind is not None

    def _parse(self) -> None:
        handlers: Mapping[str, Callable[[], bool]] = {
            "magic": self._read_magic,
            "header": self._read_header,
            "record": self._read_record,
            "payload": self._read_payload,
        }
        while True:
            handler = handlers.get(self._state)
            if handler is None or not handler():
                return

    def _read_magic(self) -> bool:
        if len(self._buffer) < 4:
            return False
        found = PCAP_MAGICS.get(bytes(self._buffer[:4]))
        self.magic_decided = True
        if found is None:
            self._state = "done"
            return False
        self.kind, self._endian, self._divisor = found
        self._state = "header" if self.kind == "pcap" else "done"
        return self.kind == "pcap"

    def _read_header(self) -> bool:
        if len(self._buffer) < 24:
            return False
        del self._buffer[:24]
        self._state = "record"
        return True

    def _read_record(self) -> bool:
        if len(self._buffer) < 16:
            return False
        seconds, fraction, captured, _original = struct.unpack(
            self._endian + "IIII", bytes(self._buffer[:16])
        )
        if captured > MAX_RECORD_BYTES:
            self._state = "done"
            return False
        stamp = seconds * 1000 + fraction // self._divisor
        if self.first_ts_ms is None:
            self.first_ts_ms = stamp
        self.last_ts_ms = stamp
        del self._buffer[:16]
        self._skip = captured
        self._state = "payload"
        return True

    def _read_payload(self) -> bool:
        take = min(self._skip, len(self._buffer))
        del self._buffer[:take]
        self._skip -= take
        if self._skip:
            return False
        self._state = "record"
        return True


class UploadCollector:
    def __init__(self, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
        self.max_bytes = max_bytes
        self.scanner = CaptureScanner()
        self.meta: bytearray | None = None
        self.filename: str | None = None
        self.saw_file = False
        self._field = bytearray()
        self._value = bytearray()
        self._headers: dict[bytes, bytes] = {}
        self._part: str | None = None

    def callbacks(self) -> "MultipartCallbacks":
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
        }

    def on_part_begin(self) -> None:
        self._headers.clear()
        self._field.clear()
        self._value.clear()
        self._part = None

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[bytes(self._field).lower()] = bytes(self._value)
        self._field.clear()
        self._value.clear()

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._headers.get(b"content-disposition", b""))
        name = options.get(b"name", b"").decode("utf-8", "replace")
        self._part = name
        if name == "file":
            self.saw_file = True
            self.filename = options.get(b"filename", b"").decode("utf-8", "replace") or None
        elif name == "meta":
            self.meta = bytearray()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = bytes(data[start:end])
        if self._part == "file":
            if self.scanner.size + len(chunk) > self.max_bytes:
                raise too_large()
            self.scanner.feed(chunk)
            if self.scanner.magic_decided and not self.scanner.is_capture:
                raise not_a_capture()
        elif self._part == "meta" and self.meta is not None:
            if len(self.meta) + len(chunk) > MAX_META_BYTES:
                raise DomainError(422, "bad_meta", "The 'meta' part is too large.")
            self.meta += chunk

    def on_part_end(self) -> None:
        self._part = None

    def meta_text(self) -> str | None:
        return None if self.meta is None else bytes(self.meta).decode("utf-8", "replace")


async def read_upload(
    request: Request,
    *,
    max_bytes: int | None = None,
    rate_bps: int | None = None,
) -> UploadCollector:
    max_bytes = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    rate_bps = READ_RATE_BPS if rate_bps is None else rate_bps
    media, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if media != b"multipart/form-data" or not boundary:
        raise DomainError(
            422,
            "bad_multipart",
            "POST /v1/imports takes multipart/form-data with a 'file' and a 'meta' part.",
        )
    declared = request.headers.get("content-length")
    if declared is not None:
        with suppress(ValueError):
            if int(declared) > max_bytes:
                raise too_large()
    collector = UploadCollector(max_bytes)
    parser = MultipartParser(boundary, callbacks=collector.callbacks())
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            parser.write(chunk)
            if rate_bps > 0:
                await asyncio.sleep(len(chunk) / rate_bps)
        parser.finalize()
    except MultipartParseError as exc:
        raise DomainError(
            422,
            "bad_multipart",
            "The multipart body is malformed; check the boundary and the part headers.",
            extra={"reason": str(exc)},
        ) from exc
    return collector


@dataclass(slots=True)
class ImportRecord:
    id: str
    label: str
    tz: str
    sha256: str
    size: int
    sensor_id: str
    first_ts_ms: int
    last_ts_ms: int
    duration_s: float
    expected_sessions: int
    created_mono: float
    state: ImportState = "received"
    started_mono: float | None = None
    sessions_indexed: int = 0
    registered: bool = field(default=False, repr=False)


class ImportStore:
    def __init__(
        self,
        clock: CaptureClock,
        time_source: TimeSource,
        world: Callable[[], World | None],
        seed: str,
    ) -> None:
        self._clock = clock
        self._time = time_source
        self._world = world
        self._seed = seed
        self._records: dict[str, ImportRecord] = {}
        self._counter = 0
        self._free_mono = 0.0

    def _new_id(self) -> str:
        self._counter += 1
        digest = hashlib.blake2b(
            f"{self._seed}|import|{self._counter}".encode(), digest_size=6
        ).hexdigest()
        return f"imp_{digest}"

    def default_window(self) -> tuple[int, int]:
        return self._clock.epoch_ms - HOUR_MS, self._clock.epoch_ms

    @staticmethod
    def index_duration_s(sha256: str) -> float:
        span = MAX_INDEX_S - MIN_INDEX_S
        return MIN_INDEX_S + (int(sha256[:8], 16) % 1000) / 1000 * span

    def by_sha256(self, sha256: str) -> ImportRecord | None:
        wanted = sha256.lower()
        return next((r for r in self._records.values() if r.sha256 == wanted), None)

    def create(
        self,
        *,
        label: str,
        tz: str,
        sha256: str,
        size: int,
        first_ts_ms: int | None,
        last_ts_ms: int | None,
    ) -> ImportRecord:
        fallback = self.default_window()
        first = first_ts_ms if first_ts_ms is not None else fallback[0]
        last = last_ts_ms if last_ts_ms is not None else fallback[1]
        if last < first:
            first, last = last, first
        record = ImportRecord(
            id=self._new_id(),
            label=label,
            tz=tz,
            sha256=sha256.lower(),
            size=size,
            sensor_id=f"imp-{len(self._records) + 1}",
            first_ts_ms=first,
            last_ts_ms=last,
            duration_s=self.index_duration_s(sha256),
            expected_sessions=min(MAX_IMPORT_SESSIONS, max(1, size // SESSION_BYTES)),
            created_mono=self._time.monotonic(),
        )
        self._records[record.id] = record
        return record

    def get(self, import_id: str) -> ImportRecord:
        self.tick()
        record = self._records.get(import_id)
        if record is None:
            raise DomainError.not_found("import_not_found", f"No import '{import_id}'.")
        return record

    def tick(self) -> None:
        now = self._time.monotonic()
        for record in self._records.values():
            if record.state == "ready":
                continue
            if record.started_mono is None:
                record.started_mono = max(record.created_mono, self._free_mono)
            if now < record.started_mono:
                return
            record.state = "indexing"
            elapsed = now - record.started_mono
            if elapsed >= record.duration_s:
                if not self._finish(record):
                    return
                continue
            share = min(1.0, elapsed / record.duration_s)
            record.sessions_indexed = int(record.expected_sessions * share)
            return

    def _finish(self, record: ImportRecord) -> bool:
        world = self._world()
        if world is None:  # pragma: no cover - the world provider starts before this one
            return False
        sensor = world.register_import(
            import_id=record.id,
            label=record.label,
            tz=record.tz,
            sha256=record.sha256,
            size=record.size,
            first_ts_ms=record.first_ts_ms,
            last_ts_ms=record.last_ts_ms,
        )
        record.sensor_id = sensor.id
        record.registered = True
        record.state = "ready"
        record.sessions_indexed = world.count(sensor.id, record.first_ts_ms, record.last_ts_ms + 1)
        return True

    def progress(self, record: ImportRecord) -> int:
        if record.state == "ready":
            return 100
        if record.started_mono is None or record.state == "received":
            return 0
        elapsed = self._time.monotonic() - record.started_mono
        return max(0, min(99, int(elapsed / record.duration_s * 100)))

    def to_model(self, record: ImportRecord) -> Import:
        return Import(
            id=record.id,
            state=record.state,
            progress=self.progress(record),
            sensor_id=record.sensor_id,
            sha256=record.sha256,
            label=record.label,
            sessions_indexed=record.sessions_indexed,
        )

    def all(self) -> list[ImportRecord]:
        return list(self._records.values())

    def reset(self) -> None:
        self._records.clear()
        self._counter = 0
        self._free_mono = 0.0

    def __len__(self) -> int:
        return len(self._records)


def get_imports(conn: HTTPConnection) -> ImportStore:
    store = getattr(conn.app.state, "imports", None)
    if not isinstance(store, ImportStore):
        raise DomainError.unavailable("imports_unavailable", "The import store is not ready.", 5)
    return store


ImportsDep = Annotated[ImportStore, Depends(get_imports)]


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:

    def world() -> World | None:
        return cast(World | None, getattr(app.state, "world", None))

    store = ImportStore(app.state.clock, app.state.time, world, app.state.settings.seed)
    app.state.imports = store

    async def poll() -> None:
        while True:
            await asyncio.sleep(POLL_S)
            store.tick()

    task = asyncio.create_task(poll())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        store.reset()
