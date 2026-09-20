from datetime import UTC, datetime
from typing import Annotated, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    PlainSerializer,
    StrictFloat,
    StrictInt,
    StrictStr,
    WithJsonSchema,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

T = TypeVar("T")


def is_none(value: object) -> bool:
    return value is None


type Scalar = StrictStr | StrictInt | StrictFloat
"""A JSON string or number (booleans are rejected)."""


class _OmitNullFromSchema:
    def __get_pydantic_json_schema__(
        self, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        branches = schema.get("anyOf")
        if isinstance(branches, list):
            kept = [b for b in branches if b != {"type": "null"}]
            if len(kept) == 1 and len(kept) != len(branches):
                rest = {k: v for k, v in schema.items() if k != "anyOf"}
                return {**kept[0], **rest}
            schema = {**schema, "anyOf": kept}
        return schema


Opt = Annotated[T | None, _OmitNullFromSchema(), Field(exclude_if=is_none)]
"""Optional-and-absent field: ``host: Opt[str] = None``. Never serialised as ``null``."""


def iso_ms(value: datetime) -> str:
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def to_epoch_ms(value: datetime) -> int:
    utc = value.astimezone(UTC)
    return int(utc.replace(microsecond=0).timestamp()) * 1000 + utc.microsecond // 1000


def from_epoch_ms(ms: int) -> datetime:
    seconds, millis = divmod(ms, 1000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=millis * 1000)


def ms_to_iso(ms: int) -> str:
    return iso_ms(from_epoch_ms(ms))


def _normalise_utc(value: datetime) -> datetime:
    utc = value.astimezone(UTC)
    return utc.replace(microsecond=utc.microsecond // 1000 * 1000)


UtcDateTime = Annotated[
    AwareDatetime,
    AfterValidator(_normalise_utc),
    PlainSerializer(iso_ms, return_type=str, when_used="json"),
    WithJsonSchema(
        {
            "type": "string",
            "format": "date-time",
            "examples": ["2025-10-27T09:14:03.120Z"],
        }
    ),
]
"""Aware datetime, UTC on the wire with millisecond precision and a ``Z`` suffix."""


class WireModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
        use_enum_values=True,
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        for prop in schema.get("properties", {}).values():
            if isinstance(prop, dict) and prop.get("default", ...) is None:
                del prop["default"]
        return schema


class RequestModel(WireModel):
    model_config = ConfigDict(extra="forbid")
