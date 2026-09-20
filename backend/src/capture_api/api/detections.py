from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.sse import EventSourceResponse, ServerSentEvent

from capture_api.deps import AuthContext, CurrentAuth, TimeDep, TokensDep, WorldDep, check_sensors
from capture_api.domain.models import DetectionList
from capture_api.errors import error_responses, json_error_responses
from capture_api.platform.observer import ObserverDep
from capture_api.realtime.bus import BusDep, ChaosDep
from capture_api.realtime.sse import DetectionStream, resume_point
from capture_api.world.types import World

router = APIRouter(tags=["detections"])

SENSOR_IDS_QUERY = Query(
    description="Comma-separated sensor ids; defaults to every sensor the caller may read.",
    examples=["hq-core,harbor-branch"],
)


def _readable(auth: AuthContext, world: World) -> frozenset[str]:
    return frozenset(sensor.id for sensor in world.sensors() if auth.can_read_sensor(sensor.id))


def sensor_filter(
    auth: CurrentAuth,
    world: WorldDep,
    sensor_ids: Annotated[str | None, SENSOR_IDS_QUERY] = None,
) -> frozenset[str]:
    requested = [part.strip() for part in (sensor_ids or "").split(",") if part.strip()]
    if not requested:
        return _readable(auth, world)
    check_sensors(auth, requested)
    return frozenset(requested)


SensorFilterDep = Annotated[frozenset[str], Depends(sensor_filter)]


@router.get(
    "/detections",
    summary="Detections released so far",
    description=(
        "Ascending by `seq`. Without `after_seq` the newest `limit` detections are returned "
        "(still ascending). `last_seq` is the head of the whole feed, so polling with "
        "`after_seq=last_seq` never re-scans detections on sensors the caller cannot read."
    ),
    response_model=DetectionList,
    responses=error_responses(401, 403, 422),
)
async def list_detections(
    world: WorldDep,
    bus: BusDep,
    sensors: SensorFilterDep,
    after_seq: Annotated[
        int | None, Query(ge=0, description="Return seq greater than this.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> DetectionList:
    items, last_seq = bus.backfill(after_seq=after_seq, limit=limit, sensor_ids=sensors)
    return DetectionList(items=[world.to_detection(d) for d in items], last_seq=last_seq)


@router.get(
    "/stream/detections",
    summary="Live detection feed (Server-Sent Events)",
    description=(
        "Opens with a `: open last_seq=<n>` comment and `retry: 3000`. A resume point "
        "(`Last-Event-ID` header, which wins, or `?last_event_id`) replays the ring of the "
        "last 1,000 detections; a resume point older than the ring yields a `reset` event "
        "instead. Live events carry `id: <seq>` and `event: detection`. The stream ends with "
        "a `reauth` event when the opening access token expires, silently when the token "
        "family is revoked, and on server rotation (300 s calm, 60 s flaky, 20 s storm)."
    ),
    response_class=EventSourceResponse,
    responses=json_error_responses(401, 403),
)
async def stream_detections(
    auth: CurrentAuth,
    *,
    world: WorldDep,
    bus: BusDep,
    tokens: TokensDep,
    chaos: ChaosDep,
    observer: ObserverDep,
    time_source: TimeDep,
    sensors: SensorFilterDep,
    last_event_id: Annotated[
        str | None, Query(description="Resume point; the Last-Event-ID header wins.")
    ] = None,
    last_event_id_header: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> AsyncIterator[ServerSentEvent]:
    stream = DetectionStream(
        bus=bus,
        world=world,
        tokens=tokens,
        chaos=chaos,
        observer=observer,
        auth=auth,
        sensor_ids=sensors,
        resume_from=resume_point(last_event_id_header, last_event_id),
        time_source=time_source,
    )
    async for event in stream.events():
        yield event
