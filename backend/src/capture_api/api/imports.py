from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from capture_api.deps import AuthContext, CurrentAuth, require_permission
from capture_api.domain.models import Import, ImportDuplicate, ImportMeta
from capture_api.errors import DomainError, error_responses
from capture_api.platform.idempotency import REPLAY_HEADER, IdempotencyDep
from capture_api.workspace.imports import ImportsDep, read_upload

router = APIRouter(tags=["imports"])

ImportCreator = Annotated[AuthContext, Depends(require_permission("imports:create"))]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", description="8-64 characters of `[A-Za-z0-9_-]`."),
]

UPLOAD_DESCRIPTION = """
`multipart/form-data` with a `file` part (`.pcap` / `.pcapng`) and a `meta` part holding
`{"label", "tz", "sha256"}` as a JSON string.

The checks run in this order, so a client can tell them apart:

1. `Content-Length` above 100 MB → **413** `too_large`, before the body is read;
2. the file's magic bytes are not pcap/pcapng → **415** `not_a_capture`;
3. the body is consumed at **8 MB/s**, so upload progress is worth drawing;
4. the SHA-256 of what arrived differs from `meta.sha256` → **422** `checksum_mismatch`;
5. that SHA-256 was imported before → **200** `{"duplicate": true, ...}`;
6. otherwise **202** and the indexing job starts.

The simulator does not dissect your capture: once the job is ready the import shows up as a
sensor whose sessions are synthesised from the file's SHA-256, inside the capture's own time
range (a pcapng is placed in `[T-1h, T]`).
"""


def _missing(field: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "missing", "loc": ["body", field], "msg": "Field required"}]
    )


@router.post(
    "/imports",
    summary="Import a capture file",
    description=UPLOAD_DESCRIPTION,
    status_code=status.HTTP_202_ACCEPTED,
    response_model=None,
    responses={
        200: {"model": ImportDuplicate, "description": "This capture was already imported"},
        202: {"model": Import, "description": "Accepted; indexing started"},
        **error_responses(401, 403, 413, 415, 422),
    },
)
async def create_import(
    request: Request,
    auth: ImportCreator,
    imports: ImportsDep,
    idempotency: IdempotencyDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    key = idempotency.validate_key(idempotency_key)
    upload = await read_upload(request)
    if not upload.saw_file:
        raise _missing("file")
    text = upload.meta_text()
    if text is None:
        raise _missing("meta")
    try:
        meta = ImportMeta.model_validate_json(text)
    except ValidationError as exc:
        errors: list[dict[str, Any]] = [
            {"type": error["type"], "loc": ["body", "meta", *error["loc"]], "msg": error["msg"]}
            for error in exc.errors()
        ]
        raise RequestValidationError(errors) from exc

    digest = upload.scanner.hexdigest()
    if digest != meta.sha256:
        raise DomainError(
            422,
            "checksum_mismatch",
            "The uploaded bytes do not match the SHA-256 declared in 'meta'.",
            extra={"expected": meta.sha256, "actual": digest},
        )

    fingerprint = idempotency.fingerprint(
        {"label": meta.label, "tz": meta.tz, "sha256": meta.sha256}
    )
    if key is not None:
        hit = idempotency.lookup("imports", auth.family_id, key, fingerprint)
        if hit is not None:
            record = imports.get(str(hit.value))
            return JSONResponse(
                imports.to_model(record).model_dump(mode="json"),
                status_code=status.HTTP_200_OK,
                headers={REPLAY_HEADER: "true"},
            )

    existing = imports.by_sha256(digest)
    if existing is not None:
        return JSONResponse(
            ImportDuplicate(
                duplicate=True, id=existing.id, sensor_id=existing.sensor_id
            ).model_dump(mode="json"),
            status_code=status.HTTP_200_OK,
        )

    scanner = upload.scanner
    record = imports.create(
        label=meta.label,
        tz=meta.tz,
        sha256=digest,
        size=scanner.size,
        first_ts_ms=scanner.first_ts_ms,
        last_ts_ms=scanner.last_ts_ms,
    )
    if key is not None:
        idempotency.remember("imports", auth.family_id, key, fingerprint, record.id)
    return JSONResponse(
        imports.to_model(record).model_dump(mode="json"),
        status_code=status.HTTP_202_ACCEPTED,
        headers={"Location": f"/v1/imports/{record.id}"},
    )


@router.get(
    "/imports/{import_id}",
    summary="Import job state",
    description=(
        "`state` walks `received` → `indexing` → `ready`; indexing takes 5-10 s. When it is "
        'ready the import is a sensor (`kind: "import"`) listed by `GET /v1/sensors`.'
    ),
    response_model=Import,
    responses=error_responses(401, 404),
)
async def get_import(import_id: str, imports: ImportsDep, _auth: CurrentAuth) -> Import:
    return imports.to_model(imports.get(import_id))
