from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from capture_api.api.admin import ChaosDep
from capture_api.deps import AuthContext, CurrentAuth, RateLimiterDep, require_permission
from capture_api.domain.models import (
    Case,
    CaseCreate,
    CaseList,
    CasePatch,
    EvidenceCreate,
    EvidenceDuplicate,
    Export,
    Note,
    NoteCreate,
)
from capture_api.errors import DomainError, ErrorBody, error_responses
from capture_api.platform.idempotency import REPLAY_HEADER, IdempotencyDep
from capture_api.workspace.cases import CasesDep
from capture_api.workspace.exports import ZIP_MEDIA_TYPE, ExportsDep
from capture_api.workspace.hunts import etag
from capture_api.world.files import content_disposition

router = APIRouter(tags=["cases"])

CaseWriter = Annotated[AuthContext, Depends(require_permission("cases:write"))]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description='The case\'s current ETag, e.g. `"v7"`.',
        examples=['"v7"'],
    ),
]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", description="8-64 characters of `[A-Za-z0-9_-]`."),
]

MERGE_PATCH = (
    "JSON merge-patch over `{title, status, severity, summary, owner_id}`; `summary: null` "
    "removes the summary. `If-Match` is REQUIRED (428 without it, 412 `etag_mismatch` with a "
    "stale tag). Cases are shared, and the teammate bot edits CASE-0002 every 90 s, so a "
    "client that caches an ETag will meet a 412 sooner or later."
)


@router.get(
    "/cases",
    summary="List cases",
    description="Newest first. Cases are shared by the whole team; observers may read them.",
    response_model=CaseList,
    responses=error_responses(400, 401),
)
async def list_cases(
    cases: CasesDep,
    _auth: CurrentAuth,
    cursor: Annotated[str | None, Query(description="Opaque cursor of the next page.")] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> CaseList:
    items, next_cursor = cases.page(cursor, limit)
    return CaseList(items=items, next_cursor=next_cursor)


@router.post(
    "/cases",
    summary="Open a case",
    status_code=status.HTTP_201_CREATED,
    response_model=Case,
    responses=error_responses(401, 403, 409, 422),
)
async def create_case(
    body: CaseCreate, response: Response, auth: CaseWriter, cases: CasesDep
) -> Case:
    case = cases.create(auth.user_id, body)
    response.headers["Location"] = f"/v1/cases/{case.id}"
    response.headers["ETag"] = etag(case.version)
    return case


@router.get(
    "/cases/{case_id}",
    summary="Read one case",
    response_model=Case,
    responses=error_responses(401, 404),
)
async def get_case(case_id: str, response: Response, cases: CasesDep, _auth: CurrentAuth) -> Case:
    case = cases.get(case_id)
    response.headers["ETag"] = etag(case.version)
    return case


@router.patch(
    "/cases/{case_id}",
    summary="Update a case",
    description=MERGE_PATCH,
    response_model=Case,
    responses=error_responses(401, 403, 404, 409, 412, 422, 428),
)
async def update_case(
    case_id: str,
    body: CasePatch,
    *,
    response: Response,
    auth: CaseWriter,
    cases: CasesDep,
    if_match: IfMatch = None,
) -> Case:
    _ = auth
    case = cases.patch(case_id, body, if_match)
    response.headers["ETag"] = etag(case.version)
    return case


@router.post(
    "/cases/{case_id}/evidence",
    summary="Pin a session as evidence",
    description=(
        '201 with the updated case, or 200 `{"duplicate": true}` when that session is '
        "already pinned (pinning twice changes nothing, not even the version)."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=None,
    responses={
        200: {"model": EvidenceDuplicate, "description": "Already pinned"},
        201: {"model": Case, "description": "Pinned"},
        **error_responses(401, 403, 404, 422),
    },
)
async def pin_evidence(
    case_id: str, body: EvidenceCreate, auth: CaseWriter, cases: CasesDep
) -> JSONResponse:
    case, duplicate = cases.pin(case_id, body, auth.user_id)
    if duplicate:
        return JSONResponse(
            EvidenceDuplicate(duplicate=True).model_dump(mode="json"),
            status_code=status.HTTP_200_OK,
            headers={"ETag": etag(case.version)},
        )
    return JSONResponse(
        case.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        headers={"ETag": etag(case.version)},
    )


@router.delete(
    "/cases/{case_id}/evidence/{session_id}",
    summary="Unpin a session",
    description="Always 204 for an existing case, whether or not that session was pinned.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404),
)
async def unpin_evidence(
    case_id: str, session_id: str, auth: CaseWriter, cases: CasesDep
) -> Response:
    _ = auth
    cases.unpin(case_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/cases/{case_id}/notes",
    summary="Append a note",
    description="Notes are append-only; adding one bumps the case version.",
    status_code=status.HTTP_201_CREATED,
    response_model=Note,
    responses=error_responses(401, 403, 404, 422),
)
async def add_note(
    case_id: str, body: NoteCreate, response: Response, auth: CaseWriter, cases: CasesDep
) -> Note:
    case, note = cases.add_note(case_id, body.body, auth.user_id)
    response.headers["ETag"] = etag(case.version)
    return note


@router.post(
    "/cases/{case_id}/exports",
    summary="Export a case",
    description=(
        "Starts a background job and answers 202. Poll `GET /v1/exports/{id}` until `state` "
        "is `ready`, then download the zip. Sending the same `Idempotency-Key` again returns "
        "the same job with `Idempotent-Replayed: true`."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Export,
    responses=error_responses(401, 403, 404, 422),
)
async def create_export(
    case_id: str,
    *,
    response: Response,
    auth: CaseWriter,
    cases: CasesDep,
    exports: ExportsDep,
    idempotency: IdempotencyDep,
    idempotency_key: IdempotencyKey = None,
) -> Export:
    case = cases.get(case_id)
    key = idempotency.validate_key(idempotency_key)
    fingerprint = idempotency.fingerprint({"case_id": case.id})
    if key is not None:
        hit = idempotency.lookup("exports", auth.family_id, key, fingerprint)
        if hit is not None:
            record = exports.get(str(hit.value))
            response.status_code = status.HTTP_200_OK
            response.headers[REPLAY_HEADER] = "true"
            return exports.to_model(record)
    record = exports.create(case)
    if key is not None:
        idempotency.remember("exports", auth.family_id, key, fingerprint, record.id)
    response.headers["Location"] = f"/v1/exports/{record.id}"
    return exports.to_model(record)


@router.get(
    "/exports/{export_id}",
    summary="Export job state",
    description="404 `export_expired` once the bundle is older than 15 minutes.",
    response_model=Export,
    responses=error_responses(401, 403, 404),
)
async def get_export(export_id: str, auth: CaseWriter, exports: ExportsDep) -> Export:
    _ = auth
    return exports.to_model(exports.get(export_id))


@router.get(
    "/exports/{export_id}/file",
    summary="Download the export bundle",
    description=(
        "A streamed zip holding `evidence.json`, `report.html`, `pcaps/<session>.pcap` for "
        "the sessions whose PCAP is still retained, and `files/<name>`. The filename comes "
        "from the case title, so it needs `filename*` when the title is not ASCII."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {ZIP_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "The export bundle",
        },
        409: {"model": ErrorBody, "description": "The export is not ready yet"},
        **error_responses(401, 403, 404, 429, 503),
    },
)
async def download_export(
    export_id: str,
    auth: CaseWriter,
    exports: ExportsDep,
    chaos: ChaosDep,
    limiter: RateLimiterDep,
) -> StreamingResponse:
    if chaos.pcap_degraded:
        raise DomainError.unavailable(
            "pcap_store_degraded",
            "The packet store is degraded; export downloads are unavailable.",
            30,
        )
    limiter.check("download", auth.family_id)
    record = exports.archive(export_id)
    return StreamingResponse(
        exports.stream(record),
        media_type=ZIP_MEDIA_TYPE,
        headers={"Content-Disposition": content_disposition(record.filename)},
    )
