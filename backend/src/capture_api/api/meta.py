from typing import Annotated, cast

from fastapi import APIRouter, Path, Request

from capture_api.deps import CurrentAuth, WorldDep, known_sensor_ids
from capture_api.domain.models import (
    ColumnList,
    EnumName,
    EnumResponse,
    EnumValue,
    FieldDef,
    FieldList,
    ProtocolSchema,
)
from capture_api.errors import DomainError, error_responses
from capture_api.world.catalog import COLUMN_DEFS, ENUM_NAMES, FIELD_DEFS, enum_values

router = APIRouter(tags=["meta"])

WARMING_RETRY_AFTER_S = 2
WARMING_ENUM = "country"
WARM_FAMILIES_ATTRIBUTE = "meta_warmed_families"


def _sensor_aware_fields(request: Request) -> list[FieldDef]:
    sensor_ids = known_sensor_ids(request)
    return [
        definition.model_copy(update={"enum": sensor_ids})
        if definition.name == "sensor"
        else definition
        for definition in FIELD_DEFS
    ]


def _warmed_families(request: Request) -> set[str]:
    state = request.app.state
    warmed: set[str] | None = getattr(state, WARM_FAMILIES_ATTRIBUTE, None)
    if warmed is None:
        warmed = set()
        setattr(state, WARM_FAMILIES_ATTRIBUTE, warmed)
    return warmed


@router.get(
    "/meta/fields",
    summary="Filter fields the search accepts",
    description=(
        "The filter catalogue: every field, its type, the operators it allows and, where it "
        "is closed, its enum. Build filter UI from this rather than from a copy in the "
        "client. The `sensor` field's enum includes ready imports."
    ),
    response_model=FieldList,
    responses=error_responses(401),
)
async def list_fields(request: Request, _auth: CurrentAuth) -> FieldList:
    return FieldList(items=_sensor_aware_fields(request))


@router.get(
    "/meta/columns",
    summary="Grid columns in their default order",
    description=(
        "The session grid's columns, in default order, with default visibility, sortability "
        "and a width hint. One column carries a `type` that is not in the documented list: "
        "render unknown types as text."
    ),
    response_model=ColumnList,
    responses=error_responses(401),
)
async def list_columns(_auth: CurrentAuth) -> ColumnList:
    return ColumnList(items=list(COLUMN_DEFS))


@router.get(
    "/meta/enums/{name}",
    summary="Values of one closed enum",
    description=(
        "Values and labels of a closed field. The FIRST `country` call of each token family "
        "answers 503 `catalog_warming` with `Retry-After: 2` while the geo catalogue loads — "
        "retry it once and it succeeds."
    ),
    response_model=EnumResponse,
    responses=error_responses(401, 404, 503),
)
async def get_enum(
    request: Request,
    auth: CurrentAuth,
    name: Annotated[str, Path(description="One of " + ", ".join(ENUM_NAMES))],
) -> EnumResponse:
    values = enum_values(name)
    if values is None:
        raise DomainError.not_found("unknown_enum", f"There is no enum '{name}'.")
    if name == WARMING_ENUM:
        warmed = _warmed_families(request)
        if auth.family_id not in warmed:
            warmed.add(auth.family_id)
            raise DomainError.unavailable(
                "catalog_warming",
                "The geo catalogue is still loading; retry in a moment.",
                WARMING_RETRY_AFTER_S,
            )
    return EnumResponse(
        name=cast(EnumName, name),
        values=[EnumValue(value=value, label=label) for value, label in values],
    )


@router.get(
    "/meta/schema/{protocol}",
    summary="Declared fields of a decoded protocol",
    description=(
        "The paths a decoded payload declares for this protocol, for both decoder "
        "generations. The decoder emits a few fields that are NOT declared here (for example "
        "`tls.ja4`): show them, but show them as undeclared."
    ),
    response_model=ProtocolSchema,
    responses=error_responses(401, 404),
)
async def get_protocol_schema(
    world: WorldDep,
    _auth: CurrentAuth,
    protocol: Annotated[str, Path(description="Protocol name, e.g. `dns`.")],
) -> ProtocolSchema:
    schema = world.protocol_schema(protocol)
    if schema is None:
        raise DomainError.not_found("unknown_protocol", f"There is no protocol '{protocol}'.")
    return schema
