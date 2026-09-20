from fastapi import APIRouter, Request

from capture_api import __version__
from capture_api.deps import ClockDep
from capture_api.domain.models import ComponentStatus, Health, HealthComponents
from capture_api.platform.chaos import COMPONENT_NAMES, ChaosController

router = APIRouter(tags=["platform"])


def _components(request: Request) -> dict[str, ComponentStatus]:
    controller = getattr(request.app.state, "chaos", None)
    if isinstance(controller, ChaosController):
        return controller.components()
    return {name: ComponentStatus(status="ok") for name in COMPONENT_NAMES}


@router.get(
    "/health",
    summary="Liveness and component status",
    description=(
        "Always answers 200, even while components are degraded, and never needs "
        "authentication. `server_time` is the CAPTURE clock, not the wall clock: use it to "
        "place the live tail. Chaos profiles degrade components (`storm` the index, "
        "`degraded-pcap` the packet store). Poll it at most every 10 seconds."
    ),
    response_model=Health,
)
async def get_health(request: Request, clock: ClockDep) -> Health:
    components = _components(request)
    degraded = any(component.status == "degraded" for component in components.values())
    return Health(
        status="degraded" if degraded else "ok",
        components=HealthComponents(
            index=components["index"],
            decoder=components["decoder"],
            pcap_store=components["pcap_store"],
            live_feed=components["live_feed"],
        ),
        server_time=clock.now(),
        version=__version__,
    )
