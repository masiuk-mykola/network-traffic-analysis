from typing import Annotated

from fastapi import APIRouter, Path, Query

from capture_api.api.searches import (
    FilterQuery,
    FromQuery,
    ReadSessions,
    SearchesDep,
    SensorsQuery,
    ToQuery,
    resolve_sensors,
    window_of,
)
from capture_api.deps import CurrentAuth, RateLimiterDep, WorldDep
from capture_api.domain.models import (
    FilterCond,
    Histogram,
    LqlParseRequest,
    LqlParseResponse,
    PivotOccurrences,
    SearchGraph,
)
from capture_api.errors import error_responses
from capture_api.search import grammar, lql
from capture_api.search.analytics import (
    DEFAULT_GRAPH_NODES,
    MAX_BUCKET_S,
    MAX_BUCKETS,
    MIN_BUCKET_S,
    bucket_count,
    conversation_graph,
    histogram,
    pivot_occurrences,
)
from capture_api.search.compile import compile_for_world, validate_filter
from capture_api.search.jobs import bad_range

router = APIRouter(tags=["analytics"])

BucketQuery = Annotated[
    int,
    Query(
        alias="bucket_s",
        ge=MIN_BUCKET_S,
        le=MAX_BUCKET_S,
        description="Bucket width in seconds (60-86400); at most 2000 buckets per request.",
    ),
]


@router.post(
    "/lql/parse",
    summary="Parse a query into a filter",
    description=(
        "Translates the query language into the `FilterNode` that `POST /v1/searches` takes, "
        "and returns the canonical re-print in `normalized`. Errors are 422 `lql_syntax` "
        "with `ctx: {pos, end}`, the character span to underline."
    ),
    response_model=LqlParseResponse,
    responses=error_responses(401, 422),
)
async def parse_lql(body: LqlParseRequest, _auth: CurrentAuth) -> LqlParseResponse:
    try:
        node, normalized = lql.parse(body.q)
    except lql.LqlError as exc:
        raise exc.as_domain_error() from exc
    return LqlParseResponse(filter=node, normalized=normalized)


@router.get(
    "/histogram",
    summary="Matching sessions over time",
    description=(
        "Counts matching sessions per protocol per time bucket. Buckets in which the sensors "
        "captured NOTHING are omitted rather than reported as zero — a capture gap is not a "
        "quiet period — and `coverage` says how much of a bucket was captured. The bucket "
        "the capture clock is inside is flagged `partial`."
    ),
    response_model=Histogram,
    responses=error_responses(400, 401, 403, 422, 429),
)
async def get_histogram(
    *,
    auth: CurrentAuth,
    world: WorldDep,
    limiter: RateLimiterDep,
    from_: FromQuery,
    to: ToQuery,
    bucket_s: BucketQuery = 300,
    sensors: SensorsQuery = None,
    f: FilterQuery = None,
) -> Histogram:
    limiter.check("analytics", auth.family_id)
    sensor_ids = resolve_sensors(world, auth, sensors)
    from_ms, to_ms = window_of(world, from_, to)
    _check_buckets(from_ms, to_ms, bucket_s)
    predicate = compile_for_world(grammar.parse_filter(f or []), world)
    return Histogram(
        bucket_s=bucket_s,
        buckets=histogram(
            world,
            sensor_ids,
            from_ms,
            to_ms,
            bucket_s=bucket_s,
            predicate=predicate,
            now_ms=world.capture_now_ms(),
        ),
    )


@router.get(
    "/pivot/occurrences",
    summary="Occurrences of one value over time, per sensor",
    description=(
        "How often one field value shows up per bucket, split by sensor — the 'where else "
        "did this happen?' chart. Buckets with no occurrences are omitted."
    ),
    response_model=PivotOccurrences,
    responses=error_responses(400, 401, 403, 422, 429),
)
async def get_pivot_occurrences(
    *,
    auth: CurrentAuth,
    world: WorldDep,
    limiter: RateLimiterDep,
    from_: FromQuery,
    to: ToQuery,
    field: Annotated[str, Query(description="A filter field name, e.g. `tls.ja3`.")],
    value: Annotated[str, Query(description="The value to count.")],
    bucket_s: BucketQuery = 300,
    sensors: SensorsQuery = None,
) -> PivotOccurrences:
    limiter.check("analytics", auth.family_id)
    sensor_ids = resolve_sensors(world, auth, sensors)
    from_ms, to_ms = window_of(world, from_, to)
    _check_buckets(from_ms, to_ms, bucket_s)
    condition = FilterCond(field=field, op="eq", value=value)
    validate_filter(condition, ("query", "field"))
    predicate = compile_for_world(condition, world)
    return PivotOccurrences(
        series=pivot_occurrences(
            world, sensor_ids, from_ms, to_ms, bucket_s=bucket_s, predicate=predicate
        )
    )


@router.get(
    "/searches/{search_id}/graph",
    summary="Conversation graph of a search",
    description=(
        "The busiest addresses in a search's results and the conversations between them. "
        "`partial` is true while the search is still running or when nodes were dropped by "
        "`limit_nodes`."
    ),
    response_model=SearchGraph,
    responses=error_responses(401, 404, 410),
)
async def get_search_graph(
    *,
    auth: ReadSessions,
    world: WorldDep,
    searches: SearchesDep,
    search_id: Annotated[str, Path(description="Search id.")],
    limit_nodes: Annotated[int, Query(ge=2, le=500, description="Most addresses to keep.")] = (
        DEFAULT_GRAPH_NODES
    ),
) -> SearchGraph:
    job = searches.get(search_id, auth.user_id)
    return conversation_graph(
        world,
        searches.matched_rows(job),
        limit_nodes=limit_nodes,
        running=not job.finished,
    )


def _check_buckets(from_ms: int, to_ms: int, bucket_s: int) -> None:
    if bucket_count(from_ms, to_ms, bucket_s * 1_000) > MAX_BUCKETS:
        raise bad_range(f"That window needs more than {MAX_BUCKETS} buckets; widen `bucket_s`.")
