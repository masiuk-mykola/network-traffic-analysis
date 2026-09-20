from typing import Annotated

from fastapi import APIRouter, Depends, Request, WebSocket, status

from capture_api.deps import (
    AuthContext,
    SettingsDep,
    TimeDep,
    TokensDep,
    WorldDep,
    check_sensors,
    require_permission,
)
from capture_api.domain.models import LiveTicketRequest, LiveTicketResponse
from capture_api.errors import DomainError, error_responses
from capture_api.platform.observer import ObserverDep
from capture_api.realtime.bus import ChaosDep
from capture_api.realtime.ws import LiveDep, serve

router = APIRouter(tags=["live"])

LiveReader = Annotated[AuthContext, Depends(require_permission("live:read"))]


def _ws_url(request: Request) -> str:
    scheme = "wss" if request.url.scheme == "https" else "ws"
    return f"{scheme}://{request.url.netloc}/v1/live"


@router.post(
    "/live/tickets",
    summary="Mint a single-use live-tap ticket",
    description=(
        "The ticket is valid for 30 seconds, survives exactly one handshake and is bound to "
        "the caller's token family and the requested sensors. Revoking the family closes "
        "every socket it opened."
    ),
    status_code=status.HTTP_201_CREATED,
    response_model=LiveTicketResponse,
    responses=error_responses(401, 403, 422),
)
async def create_live_ticket(
    body: LiveTicketRequest,
    request: Request,
    auth: LiveReader,
    world: WorldDep,
    live: LiveDep,
) -> LiveTicketResponse:
    known = {sensor.id for sensor in world.sensors()}
    for index, sensor_id in enumerate(body.sensor_ids):
        if sensor_id not in known:
            raise DomainError(
                422,
                "unknown_sensor",
                f"No sensor {sensor_id}.",
                extra={"loc": ["body", "sensor_ids", index]},
            )
    check_sensors(auth, body.sensor_ids)
    ticket = live.issue(family_id=auth.family_id, user=auth.user, sensor_ids=body.sensor_ids)
    return LiveTicketResponse(
        ticket=ticket.ticket, expires_in=int(live.ttl_s), ws_url=_ws_url(request)
    )


@router.websocket("/live")
async def live_tap(
    websocket: WebSocket,
    *,
    world: WorldDep,
    live: LiveDep,
    chaos: ChaosDep,
    observer: ObserverDep,
    tokens: TokensDep,
    settings: SettingsDep,
    time_source: TimeDep,
    ticket: str | None = None,
) -> None:
    await serve(
        websocket,
        ticket=ticket,
        allowed_origins=settings.allowed_origins,
        live=live,
        world=world,
        chaos=chaos,
        observer=observer,
        tokens=tokens,
        time_source=time_source,
    )
