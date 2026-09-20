import base64
import hashlib
import hmac
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse

from capture_api.deps import (
    AuthContext,
    RateLimiterDep,
    SettingsDep,
    WorldDep,
    check_sensors,
    require_permission,
)
from capture_api.domain.base import ms_to_iso
from capture_api.domain.models import (
    FlowSample,
    RelatedSessions,
    RelatedWindow,
    Session,
    SessionFlow,
)
from capture_api.errors import DomainError, error_responses
from capture_api.platform.chaos import ChaosController
from capture_api.world.files import content_disposition, trap_payload
from capture_api.world.ids import parse_session_id
from capture_api.world.types import Row, World

router = APIRouter(tags=["sessions"])

CHUNK_BYTES = 64 * 1024
"""Download chunk size; small enough that a client sees progress on a 6 MB file."""

PCAP_MEDIA_TYPE = "application/vnd.tcpdump.pcap"
PCAP_DEGRADED_RETRY_S = 30

RELATED_PAGE = 100
RELATED_WINDOW_MS: dict[str, int] = {"15m": 900_000, "1h": 3_600_000, "6h": 21_600_000}


def binary_response(*media_types: str) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": "Streamed body (chunked, no Content-Length).",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in media_types
            },
            "headers": {
                "Content-Disposition": {
                    "description": "attachment; filename=\"<ascii>\"; filename*=UTF-8''<encoded>",
                    "schema": {"type": "string"},
                },
                "X-Content-SHA256": {
                    "description": "SHA-256 of the exact bytes sent.",
                    "schema": {"type": "string"},
                },
            },
        }
    }


SessionReader = Annotated[AuthContext, Depends(require_permission("sessions:read"))]
FileDownloader = Annotated[AuthContext, Depends(require_permission("files:download"))]
PcapDownloader = Annotated[AuthContext, Depends(require_permission("pcap:download"))]


def _row(world: World, auth: AuthContext, session_id: str) -> Row:
    parsed = parse_session_id(session_id)
    row = world.row(parsed) if parsed is not None else None
    if row is None:
        raise DomainError.not_found(
            "session_not_found", f"No session '{session_id}' on any readable sensor."
        )
    check_sensors(auth, [row.sensor_id])
    return row


def _chunks(payload: bytes) -> Iterator[bytes]:
    for offset in range(0, len(payload), CHUNK_BYTES):
        yield payload[offset : offset + CHUNK_BYTES]


def _download(payload: bytes, *, media_type: str, name: str, sha256: str) -> StreamingResponse:
    return StreamingResponse(
        _chunks(payload),
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition(name),
            "X-Content-SHA256": sha256,
        },
    )


def _pcap_degraded(request: Request) -> bool:
    controller = getattr(request.app.state, "chaos", None)
    return isinstance(controller, ChaosController) and controller.pcap_degraded


def _pcap_name(world: World, row: Row) -> str:
    sensor = world.sensor(row.sensor_id)
    label = "-".join((sensor.name if sensor else row.sensor_id).split())
    return f"capture_api-{label}-{row.id}.pcap"


def _sign(key: bytes, binding: str, payload: str) -> str:
    return hmac.new(key, f"{binding}|{payload}".encode(), hashlib.sha256).hexdigest()[:16]


def _encode_cursor(key: bytes, binding: str, start_ms: int, row_id: int) -> str:
    payload = f"{start_ms}.{row_id}"
    raw = f"{payload}.{_sign(key, binding, payload)}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(key: bytes, binding: str, cursor: str) -> tuple[int, int]:
    position = _read_cursor(key, binding, cursor)
    if position is None:
        raise DomainError(
            400,
            "invalid_cursor",
            "The cursor is not valid for this session and window; start the page again.",
        )
    return position


def _read_cursor(key: bytes, binding: str, cursor: str) -> tuple[int, int] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        start_text, id_text, signature = raw.split(".")
        start_ms, row_id = int(start_text), int(id_text)
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, _sign(key, binding, f"{start_ms}.{row_id}")):
        return None
    return start_ms, row_id


@router.get(
    "/sessions/{session_id}",
    summary="One fully decoded session",
    description=(
        "The grid row plus the decoded transaction, its detections, carved files and PCAP "
        "retention state. `decoded` follows the SENSOR's decoder: the harbor branch answers "
        "the legacy v1 shape (numbers as strings, single-element arrays collapsed to the "
        "bare object, `false` booleans omitted), everything else the canonical v2 shape. "
        'Observers see `{"redacted": true}` in place of sensitive values. Session ids are '
        "uint64 decimal strings — a malformed id is a 404, not a 422."
    ),
    response_model=Session,
    responses=error_responses(401, 403, 404),
)
async def get_session(session_id: str, auth: SessionReader, world: WorldDep) -> Session:
    return world.to_session(_row(world, auth, session_id), auth.role)


@router.get(
    "/sessions/{session_id}/flow",
    summary="Byte and packet flow of a session",
    description=(
        "Deterministic traffic samples for sparklines. **Empty buckets are omitted** — an "
        "idle gap is a missing sample, not a zero, so plot against `t` (epoch "
        "milliseconds, not an ISO string) rather than by index. Works after the PCAP has "
        "expired: flow comes from the index, not from packets."
    ),
    response_model=SessionFlow,
    responses=error_responses(401, 403, 404, 422),
)
async def get_session_flow(
    session_id: str,
    auth: SessionReader,
    world: WorldDep,
    bucket_ms: Annotated[
        int, Query(ge=100, le=60_000, description="Bucket width in milliseconds.")
    ] = 1000,
) -> SessionFlow:
    row = _row(world, auth, session_id)
    return SessionFlow(
        session_id=str(row.id),
        bucket_ms=bucket_ms,
        samples=[
            FlowSample(
                t=sample.t_ms,
                bytes_up=sample.bytes_up,
                bytes_down=sample.bytes_down,
                packets_up=sample.packets_up,
                packets_down=sample.packets_down,
            )
            for sample in world.flow(row, bucket_ms)
        ],
    )


@router.get(
    "/sessions/{session_id}/files/{file_id}",
    summary="Download a carved file",
    description=(
        "Streams the carved file (chunked, no `Content-Length`). The name in "
        "`Content-Disposition` may be non-ASCII or contain path separators: use the "
        "`filename*` value, and sanitise it before writing to disk. `X-Content-SHA256` is "
        "the digest of the bytes sent. Purged files answer 410 `file_purged`. **One seeded "
        'file answers 200 `application/json` `{"error": "extraction_failed"}`** — check '
        "the content type before saving. Downloads share a limit of 10 per minute per "
        "session family with the PCAP route."
    ),
    response_class=StreamingResponse,
    responses={
        **binary_response("application/octet-stream", "application/json"),
        **error_responses(401, 403, 404, 410, 429),
    },
)
async def download_session_file(
    session_id: str,
    file_id: str,
    auth: FileDownloader,
    world: WorldDep,
    limiter: RateLimiterDep,
) -> Response:
    row = _row(world, auth, session_id)
    limiter.check("download", auth.family_id)
    file = world.file(file_id)
    if file is None or file.session_id != row.id:
        raise DomainError.not_found(
            "file_not_found", f"Session {row.id} has no carved file '{file_id}'."
        )
    if file.trap:
        media_type, body = trap_payload()
        return Response(body, media_type=media_type)
    if file.purged:
        raise DomainError(
            410,
            "file_purged",
            f"'{file.name}' was removed from the carve store to reclaim quota.",
        )
    return _download(
        world.file_bytes(file), media_type=file.mime, name=file.name, sha256=file.sha256
    )


@router.get(
    "/sessions/{session_id}/pcap",
    summary="Download the session's packets",
    description=(
        "Streams classic libpcap bytes (the first 256 packets of the session) as "
        f"`{PCAP_MEDIA_TYPE}`. Packets are kept for 48 hours only: an older session answers "
        "410 `pcap_expired` with `expired_at`, while its metadata, flow and carved files "
        "stay available — check `pcap.available` on the session before offering the button. "
        "Imported captures are never dissected, so they answer 410 `pcap_not_captured`. "
        "Under the `degraded-pcap` chaos profile every request answers 503 "
        "`pcap_store_degraded` with `Retry-After: 30`. Shares the 10-per-minute download "
        "limit with carved files."
    ),
    response_class=StreamingResponse,
    responses={
        **binary_response(PCAP_MEDIA_TYPE),
        **error_responses(401, 403, 404, 410, 429, 503),
    },
)
async def download_session_pcap(
    session_id: str,
    request: Request,
    auth: PcapDownloader,
    world: WorldDep,
    limiter: RateLimiterDep,
) -> Response:
    row = _row(world, auth, session_id)
    if _pcap_degraded(request):
        raise DomainError.unavailable(
            "pcap_store_degraded",
            "The packet store is degraded; try again shortly.",
            PCAP_DEGRADED_RETRY_S,
        )
    limiter.check("download", auth.family_id)
    status = world.pcap_status(row)
    if not status.available:
        if status.expired_at_ms is None:
            raise DomainError(
                410,
                "pcap_not_captured",
                f"Session {row.id} comes from an imported capture; it has no packets here.",
            )
        expired_at = status.expired_at_ms
        raise DomainError(
            410,
            "pcap_expired",
            f"Packets for session {row.id} were dropped after the 48 hour retention.",
            extra={"expired_at": ms_to_iso(expired_at)},
        )
    payload = world.pcap(row)
    return _download(
        payload,
        media_type=PCAP_MEDIA_TYPE,
        name=_pcap_name(world, row),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


@router.get(
    "/sessions/{session_id}/related",
    summary="Other sessions between the same two hosts",
    description=(
        "Sessions of the same sensor between the same address pair (either direction) "
        "within ± `window` of this one, newest first, 100 per page. `next_cursor` is opaque "
        "and bound to this session and window: reusing it elsewhere answers 400 "
        "`invalid_cursor`."
    ),
    response_model=RelatedSessions,
    responses=error_responses(400, 401, 403, 404, 422),
)
async def list_related_sessions(
    session_id: str,
    *,
    auth: SessionReader,
    world: WorldDep,
    settings: SettingsDep,
    window: Annotated[RelatedWindow, Query(description="Half-width around the session.")] = "1h",
    cursor: Annotated[str | None, Query(description="From a previous page.")] = None,
) -> RelatedSessions:
    row = _row(world, auth, session_id)
    binding = f"{row.id}:{window}"
    after = _decode_cursor(settings.cursor_key, binding, cursor) if cursor else None

    half = RELATED_WINDOW_MS[window]
    pair = frozenset((row.src_ip, row.dst_ip))
    items: list[Row] = []
    next_cursor: str | None = None
    for candidate in world.rows_desc(row.sensor_id, row.start_ms - half, row.start_ms + half + 1):
        if candidate.id == row.id or frozenset((candidate.src_ip, candidate.dst_ip)) != pair:
            continue
        if after is not None and (candidate.start_ms, candidate.id) >= after:
            continue
        if len(items) == RELATED_PAGE:
            last = items[-1]
            next_cursor = _encode_cursor(settings.cursor_key, binding, last.start_ms, last.id)
            break
        items.append(candidate)
    return RelatedSessions(
        items=[world.to_session_row(item) for item in items], next_cursor=next_cursor
    )
