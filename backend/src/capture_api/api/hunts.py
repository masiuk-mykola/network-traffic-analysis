from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from capture_api.deps import AuthContext, CurrentAuth, require_permission
from capture_api.domain.models import Hunt, HuntCreate, HuntList, HuntPatch
from capture_api.errors import error_responses
from capture_api.workspace.hunts import HuntsDep, etag

router = APIRouter(tags=["hunts"])

HuntWriter = Annotated[AuthContext, Depends(require_permission("hunts:write"))]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description='The hunt\'s current ETag, e.g. `"v3"`.',
        examples=['"v3"'],
    ),
]

MERGE_PATCH = (
    "JSON merge-patch: omitted keys stay as they are and `description: null` removes the "
    "description. `Content-Type` may be `application/merge-patch+json` or plain "
    "`application/json`. `If-Match` is REQUIRED: without it the answer is 428 "
    "`precondition_required`, with a stale tag 412 `etag_mismatch` carrying the current hunt "
    "under `current` (and its `ETag` header)."
)


@router.get(
    "/hunts",
    summary="List your saved hunts",
    description="Only the caller's own hunts, newest first. Hunts are never shared.",
    response_model=HuntList,
    responses=error_responses(401),
)
async def list_hunts(auth: CurrentAuth, hunts: HuntsDep) -> HuntList:
    return HuntList(items=hunts.list(auth.user_id))


@router.post(
    "/hunts",
    summary="Save a hunt",
    description='Answers 201 with `Location` and `ETag: "v1"`.',
    status_code=status.HTTP_201_CREATED,
    response_model=Hunt,
    responses=error_responses(401, 403, 409, 422),
)
async def create_hunt(
    body: HuntCreate, response: Response, auth: HuntWriter, hunts: HuntsDep
) -> Hunt:
    hunt = hunts.create(auth.user_id, body)
    response.headers["Location"] = f"/v1/hunts/{hunt.id}"
    response.headers["ETag"] = etag(hunt.version)
    return hunt


@router.get(
    "/hunts/{hunt_id}",
    summary="Read one saved hunt",
    description="404 `hunt_not_found` for an unknown id and for another user's hunt.",
    response_model=Hunt,
    responses=error_responses(401, 404),
)
async def get_hunt(hunt_id: str, response: Response, auth: CurrentAuth, hunts: HuntsDep) -> Hunt:
    hunt = hunts.get(auth.user_id, hunt_id)
    response.headers["ETag"] = etag(hunt.version)
    return hunt


@router.patch(
    "/hunts/{hunt_id}",
    summary="Update a saved hunt",
    description=MERGE_PATCH,
    response_model=Hunt,
    responses=error_responses(401, 403, 404, 409, 412, 422, 428),
)
async def update_hunt(
    hunt_id: str,
    body: HuntPatch,
    *,
    response: Response,
    auth: HuntWriter,
    hunts: HuntsDep,
    if_match: IfMatch = None,
) -> Hunt:
    hunt = hunts.patch(auth.user_id, hunt_id, body, if_match)
    response.headers["ETag"] = etag(hunt.version)
    return hunt


@router.delete(
    "/hunts/{hunt_id}",
    summary="Delete a saved hunt",
    description="`If-Match` is optional here, but it is checked when you send it.",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 403, 404, 412),
)
async def delete_hunt(
    hunt_id: str, auth: HuntWriter, hunts: HuntsDep, if_match: IfMatch = None
) -> Response:
    hunts.delete(auth.user_id, hunt_id, if_match)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
