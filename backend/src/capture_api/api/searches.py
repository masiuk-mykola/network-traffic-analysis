from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from pydantic import AwareDatetime
from starlette.requests import HTTPConnection

from capture_api.deps import (
    AuthContext,
    CurrentAuth,
    RateLimiterDep,
    WorldDep,
    require_permission,
)
from capture_api.domain.base import to_epoch_ms
from capture_api.domain.models import (
    EstimateResponse,
    Search,
    SearchCreate,
    SearchResults,
    SortKey,
)
from capture_api.errors import DomainError, error_responses
from capture_api.platform.chaos import ChaosController
from capture_api.platform.idempotency import REPLAY_HEADER, IdempotencyDep
from capture_api.search import grammar
from capture_api.search.compile import compile_for_world, validate_filter
from capture_api.search.estimate import estimate
from capture_api.search.jobs import (
    LIMIT_HEADER,
    SearchJob,
    SearchService,
    to_model,
    validate_window,
)
from capture_api.world.types import World

router = APIRouter(tags=["search"])

IDEMPOTENCY_SCOPE = "searches"
IDEMPOTENCY_HEADER = "Idempotency-Key"


def get_searches(conn: HTTPConnection) -> SearchService:
    return cast(SearchService, conn.app.state.searches)


def get_chaos(conn: HTTPConnection) -> ChaosController | None:
    controller = getattr(conn.app.state, "chaos", None)
    return controller if isinstance(controller, ChaosController) else None


SearchesDep = Annotated[SearchService, Depends(get_searches)]
ChaosDep = Annotated[ChaosController | None, Depends(get_chaos)]
ReadSessions = Annotated[AuthContext, Depends(require_permission("sessions:read"))]

SensorsQuery = Annotated[
    str | None,
    Query(
        alias="sensors",
        description="Comma-separated sensor ids; every readable sensor when omitted.",
        examples=["hq-core,dc-east"],
    ),
]
FromQuery = Annotated[AwareDatetime, Query(alias="from", description="Window start (ISO-8601).")]
ToQuery = Annotated[AwareDatetime, Query(alias="to", description="Window end (ISO-8601).")]
FilterQuery = Annotated[
    list[str] | None,
    Query(
        alias="f",
        description="Filter rows, `<field>:<op>:<v1>,<v2>` (repeat the parameter to AND them).",
        examples=["protocol:eq:tls"],
    ),
]


def resolve_sensors(
    world: World,
    auth: AuthContext,
    raw: str | None,
    *,
    loc: tuple[str | int, ...] = ("query", "sensors"),
) -> list[str]:
    known = [sensor.id for sensor in world.sensors()]
    if raw is None or not raw.strip():
        return [sensor_id for sensor_id in known if auth.can_read_sensor(sensor_id)]
    requested = [part.strip() for part in raw.split(",") if part.strip()]
    if not requested:
        raise DomainError(422, "unknown_sensor", "No sensor was named.", extra={"loc": list(loc)})
    check_sensors_exist(world, auth, requested, loc=loc)
    return requested


def check_sensors_exist(
    world: World,
    auth: AuthContext,
    sensor_ids: list[str],
    *,
    loc: tuple[str | int, ...] = ("body", "sensor_ids"),
) -> None:
    for index, sensor_id in enumerate(sensor_ids):
        if world.sensor(sensor_id) is None:
            raise DomainError(
                422,
                "unknown_sensor",
                f"There is no sensor '{sensor_id}'.",
                extra={"loc": [*loc, index], "sensor_id": sensor_id},
            )
    for sensor_id in sensor_ids:
        if not auth.can_read_sensor(sensor_id):
            raise DomainError.forbidden_sensor(sensor_id)


def window_of(world: World, start: AwareDatetime, end: AwareDatetime) -> tuple[int, int]:
    from_ms, to_ms = to_epoch_ms(start), to_epoch_ms(end)
    validate_window(world, from_ms, to_ms)
    return from_ms, to_ms


@router.get(
    "/estimate",
    summary="Estimate how much a filter would match",
    description=(
        "Evaluates the filter on a sample of the window and scales the result, so it is fast "
        "and approximate by construction (`is_estimate` is always true). Use it to size a "
        "search before starting one; at most 4 requests per second per session."
    ),
    response_model=EstimateResponse,
    responses=error_responses(400, 401, 403, 422, 429),
)
async def get_estimate(
    *,
    auth: CurrentAuth,
    world: WorldDep,
    limiter: RateLimiterDep,
    from_: FromQuery,
    to: ToQuery,
    sensors: SensorsQuery = None,
    f: FilterQuery = None,
) -> EstimateResponse:
    limiter.check("estimate", auth.family_id)
    sensor_ids = resolve_sensors(world, auth, sensors)
    from_ms, to_ms = window_of(world, from_, to)
    node = grammar.parse_filter(f or [])
    predicate = compile_for_world(node, world)
    result = estimate(world, sensor_ids, from_ms, to_ms, predicate)
    return EstimateResponse(
        estimated_matches=result.matches,
        estimated_sessions_scanned=result.scanned,
        is_estimate=True,
    )


def _replay(response: Response, job: SearchJob) -> Search:
    response.status_code = status.HTTP_200_OK
    response.headers[REPLAY_HEADER] = "true"
    response.headers["Location"] = f"/v1/searches/{job.id}"
    return to_model(job)


@router.post(
    "/searches",
    summary="Start a search",
    description=(
        "Answers 202 with a queued Search and a `Location` header; poll it, or page its "
        "results while it runs. Send an `Idempotency-Key` so a retry after a 503 returns the "
        "search you already started (200 + `Idempotent-Replayed: true`) instead of a twin. "
        "Three concurrent searches per user; DELETE one to free its slot."
    ),
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Search,
    responses=error_responses(400, 401, 403, 422, 429, 503),
)
async def create_search(
    *,
    body: SearchCreate,
    request: Request,
    response: Response,
    auth: ReadSessions,
    world: WorldDep,
    searches: SearchesDep,
    limiter: RateLimiterDep,
    idempotency: IdempotencyDep,
    chaos: ChaosDep,
) -> Search:
    from_ms, to_ms = window_of(world, body.from_, body.to)
    check_sensors_exist(world, auth, list(body.sensor_ids))
    validate_filter(body.filter)
    limiter.check("search_create", auth.user_id)

    key = idempotency.validate_key(request.headers.get(IDEMPOTENCY_HEADER))
    fingerprint = idempotency.fingerprint(body.model_dump(mode="json"))
    if key is not None:
        record = idempotency.lookup(IDEMPOTENCY_SCOPE, auth.family_id, key, fingerprint)
        if record is not None:
            existing = searches.peek(str(record.value))
            if existing is not None:
                return _replay(response, existing)

    decision = chaos.search_decision(request) if chaos is not None else None
    if chaos is not None and decision is not None and decision.pre_commit_503:
        raise chaos.unavailable_error(decision.retry_after_s)

    job = searches.create(
        user_id=auth.user_id,
        family_id=auth.family_id,
        sensor_ids=list(body.sensor_ids),
        from_ms=from_ms,
        to_ms=to_ms,
        filter_node=body.filter,
        sort=body.sort,
        fail_during_scan=bool(decision and decision.fail_during_scan),
    )
    if key is not None:
        idempotency.remember(IDEMPOTENCY_SCOPE, auth.family_id, key, fingerprint, job.id)
    if chaos is not None and decision is not None and decision.post_commit_503:
        raise chaos.unavailable_error(decision.retry_after_s)
    response.headers["Location"] = f"/v1/searches/{job.id}"
    return to_model(job)


@router.get(
    "/searches/{search_id}",
    summary="Search state and progress",
    description=(
        "Reading a search resets its 10-minute idle timer. A search nobody reads for 10 "
        "minutes is discarded: 410 `search_expired`, and its slot is freed."
    ),
    response_model=Search,
    responses=error_responses(401, 404, 410),
)
async def get_search(
    auth: ReadSessions,
    searches: SearchesDep,
    search_id: Annotated[str, Path(description="Search id from POST /v1/searches.")],
) -> Search:
    return to_model(searches.get(search_id, auth.user_id))


@router.get(
    "/searches/{search_id}/results",
    summary="A page of matched sessions",
    description=(
        "Rows arrive in scan order (newest first) while the search runs. "
        "`next_cursor: null` with `complete: false` means *caught up* — ask again later; "
        "`complete: true` means that was the end. Cursors are opaque and bound to the "
        "search and its ordering. `limit` is clamped to 500; the effective value comes back "
        "in `X-Limit-Applied`. Sorting differently needs a finished search (409 otherwise)."
    ),
    response_model=SearchResults,
    responses=error_responses(400, 401, 404, 409, 410),
)
async def get_search_results(
    *,
    response: Response,
    auth: ReadSessions,
    searches: SearchesDep,
    search_id: Annotated[str, Path(description="Search id.")],
    cursor: Annotated[str | None, Query(description="Opaque cursor from `next_cursor`.")] = None,
    limit: Annotated[int | None, Query(description="Page size, 1-500 (default 200).")] = None,
    sort: Annotated[SortKey | None, Query(description="Only once the search is done.")] = None,
) -> SearchResults:
    job = searches.get(search_id, auth.user_id)
    page = searches.results(job, cursor=cursor, limit=limit, sort=sort)
    response.headers[LIMIT_HEADER] = str(page.limit_applied)
    return page.results


@router.delete(
    "/searches/{search_id}",
    summary="Cancel a search and free its slot",
    description=(
        "Always 204, whatever the search's state and even for ids that never existed. This "
        "is how a client gives back one of its three slots."
    ),
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401),
)
async def delete_search(
    auth: ReadSessions,
    searches: SearchesDep,
    search_id: Annotated[str, Path(description="Search id.")],
) -> Response:
    searches.cancel(search_id, auth.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
