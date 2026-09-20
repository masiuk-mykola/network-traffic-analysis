from typing import Annotated

from fastapi import APIRouter, Path

from capture_api.deps import CurrentAuth, RateLimiterDep, WorldDep
from capture_api.domain.models import EnrichRequest, EnrichResponse, EnrichResult
from capture_api.errors import error_responses
from capture_api.world.types import EnrichData

router = APIRouter(tags=["enrichment"])


def _result(data: EnrichData) -> EnrichResult:
    return EnrichResult(
        country=data.country, asn=data.asn, org=data.org, reputation=data.reputation
    )


@router.post(
    "/enrich/ips",
    summary="Enrich up to 100 addresses at once",
    description=(
        "Looks up every address in one call and answers a map keyed by the address exactly "
        "as it was sent. Internal and unparseable addresses come back with "
        '`reputation: "unknown"` and no country, ASN or org (absent keys, never null). '
        "Limited to 1 request per second per session family, so coalesce a grid page into a "
        "single call and cache the answers."
    ),
    response_model=EnrichResponse,
    responses=error_responses(401, 422, 429),
)
async def enrich_ips(
    body: EnrichRequest,
    auth: CurrentAuth,
    world: WorldDep,
    limiter: RateLimiterDep,
) -> EnrichResponse:
    limiter.check("enrich_batch", auth.family_id)
    return EnrichResponse(results={ip: _result(world.enrich(ip)) for ip in body.ips})


@router.get(
    "/enrich/ips/{ip}",
    summary="Enrich one address",
    description=(
        "The same object the batch route returns for a single address. Limited to 5 "
        "requests per second per session family; use `POST /v1/enrich/ips` for anything "
        "bigger than a detail pane."
    ),
    response_model=EnrichResult,
    responses=error_responses(401, 429),
)
async def get_ip_enrichment(
    ip: Annotated[str, Path(min_length=2, max_length=45, description="IPv4 or IPv6 address.")],
    auth: CurrentAuth,
    world: WorldDep,
    limiter: RateLimiterDep,
) -> EnrichResult:
    limiter.check("enrich_single", auth.family_id)
    return _result(world.enrich(ip))
