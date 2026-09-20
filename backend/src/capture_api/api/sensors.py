from fastapi import APIRouter, Depends

from capture_api.deps import WorldDep, current_auth
from capture_api.domain.models import SensorList
from capture_api.errors import error_responses

router = APIRouter(tags=["platform"])


@router.get(
    "/sensors",
    summary="Every capture sensor",
    description=(
        "Lists EVERY sensor, including the ones the caller may not read: use "
        "`Profile.sensor_ids` (from `GET /v1/me`) to tell readable sensors apart, and show "
        "the rest as locked rather than hiding them. Ready capture imports appear here too, "
        'with `kind: "import"`. `last_packet_at` is the newest instant the sensor has '
        "made visible (capture clock minus `lag_seconds`), while `last_packet_local` is a "
        "legacy `DD/MM/YYYY HH:mm:ss` string in the sensor's own time zone."
    ),
    response_model=SensorList,
    responses=error_responses(401),
    dependencies=[Depends(current_auth)],
)
async def list_sensors(world: WorldDep) -> SensorList:
    return SensorList(items=[world.to_sensor(sensor) for sensor in world.sensors()])
