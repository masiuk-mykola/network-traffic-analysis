import ipaddress
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from capture_api.domain.base import Scalar
from capture_api.domain.models import (
    FieldDef,
    FilterAll,
    FilterAny,
    FilterCond,
    FilterNode,
    FilterNot,
    FilterOp,
    iter_conditions,
)
from capture_api.errors import DomainError
from capture_api.world.catalog import FIELD_DEFS_BY_NAME, PROTOCOLS
from capture_api.world.enrich_data import country_for_ip
from capture_api.world.types import Row, World

type Predicate = Callable[[Row], bool]
"""A compiled filter: ``predicate(row)`` is ``True`` when the row matches."""

type ValueGetter = Callable[[Row], tuple[Any, ...]]
"""Every value a field has on a row (empty when the field is absent)."""

NUMERIC_TYPES: frozenset[str] = frozenset({"port", "number", "bytes", "duration_ms"})
"""Field types compared as integers rather than as text."""

PROTOCOL_NAMES: frozenset[str] = frozenset(name for name, _ in PROTOCOLS)

SEMANTIC_CODES: tuple[str, ...] = ("unknown_field", "operator_not_allowed", "bad_value")
"""The three 422 codes a filter can raise."""


class FilterError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _no_lookup(_ip: str) -> str | None:
    return None


@dataclass(frozen=True, slots=True)
class CompileContext:
    hostname: Callable[[str], str | None] = field(default=_no_lookup)
    country: Callable[[str], str | None] = field(default=_no_lookup)


def context_for_world(world: World) -> CompileContext:
    seed = world.seed

    def hostname(ip: str) -> str | None:
        host = world.host(ip)
        return host.hostname if host is not None else None

    def country(ip: str) -> str | None:
        host = world.host(ip)
        known = host.country if host is not None else None
        return known or country_for_ip(seed, ip)

    return CompileContext(hostname=hostname, country=country)


def operator_allowed(definition: FieldDef, op: FilterOp) -> bool:
    if op == "in":
        return "eq" in definition.operators
    return op in definition.operators


def condition_values(cond: FilterCond) -> list[Scalar]:
    if cond.values is not None:
        return list(cond.values)
    if cond.value is not None:
        return [cond.value]
    return []


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return None


def check_value(definition: FieldDef, op: FilterOp, value: Scalar) -> None:
    text = str(value)
    if op == "cidr":
        try:
            ipaddress.ip_network(text, strict=False)
        except ValueError as exc:
            raise FilterError("bad_value", f"'{text}' is not an IPv4 or IPv6 network.") from exc
        return
    if definition.type in NUMERIC_TYPES:
        if _as_int(value) is None:
            raise FilterError("bad_value", f"'{text}' is not a whole number.")
        return
    if op in ("glob", "exists"):
        return
    if definition.type == "ip":
        try:
            ipaddress.ip_address(text)
        except ValueError as exc:
            raise FilterError("bad_value", f"'{text}' is not an IP address.") from exc
        return
    if definition.enum is not None and definition.type != "sensor":
        folded = {allowed.casefold() for allowed in definition.enum}
        if text.casefold() not in folded:
            raise FilterError("bad_value", f"'{text}' is not a value of '{definition.name}'.")
        return
    if definition.pattern is not None and not re.fullmatch(definition.pattern, text, re.IGNORECASE):
        raise FilterError("bad_value", f"'{text}' does not match {definition.pattern}.")


def validate_condition(cond: FilterCond) -> None:
    definition = FIELD_DEFS_BY_NAME.get(cond.field)
    if definition is None:
        raise FilterError("unknown_field", f"'{cond.field}' is not a filter field.")
    if not operator_allowed(definition, cond.op):
        allowed = ", ".join(definition.operators)
        raise FilterError(
            "operator_not_allowed",
            f"'{cond.op}' cannot be used on '{cond.field}'; allowed: {allowed}.",
        )
    for value in condition_values(cond):
        check_value(definition, cond.op, value)


def validate_filter(node: FilterNode, loc_prefix: Sequence[str | int] = ("body", "filter")) -> None:
    for loc, cond in iter_conditions(node):
        try:
            validate_condition(cond)
        except FilterError as exc:
            raise DomainError(
                422, exc.code, exc.detail, extra={"loc": [*loc_prefix, *loc]}
            ) from exc


def _attr_values(row: Row, key: str) -> tuple[Any, ...]:
    value = row.attrs.get(key)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    return (value,)


_ROW_GETTERS: dict[str, Callable[[Row], tuple[Any, ...]]] = {
    "sensor": lambda row: (row.sensor_id,),
    "protocol": lambda row: (row.protocol,),
    "src.ip": lambda row: (row.src_ip,),
    "dst.ip": lambda row: (row.dst_ip,),
    "src.port": lambda row: (row.src_port,),
    "dst.port": lambda row: (row.dst_port,),
    "risk.score": lambda row: (row.risk_score,),
    "bytes.up": lambda row: (row.bytes_up,),
    "bytes.down": lambda row: (row.bytes_down,),
    "duration_ms": lambda row: (row.duration_ms,),
}


def value_getter(name: str, ctx: CompileContext) -> ValueGetter:
    simple = _ROW_GETTERS.get(name)
    if simple is not None:
        return simple
    if name == "host":
        hostname = ctx.hostname

        def both_hosts(row: Row) -> tuple[Any, ...]:
            return tuple(
                host for host in (hostname(row.src_ip), hostname(row.dst_ip)) if host is not None
            )

        return both_hosts
    if name == "dst.host":
        hostname = ctx.hostname

        def dst_host(row: Row) -> tuple[Any, ...]:
            host = hostname(row.dst_ip)
            return () if host is None else (host,)

        return dst_host
    if name == "dst.country":
        country = ctx.country

        def dst_country(row: Row) -> tuple[Any, ...]:
            found = country(row.dst_ip)
            return () if found is None else (found,)

        return dst_country

    def from_attrs(row: Row) -> tuple[Any, ...]:
        return _attr_values(row, name)

    return from_attrs


def protocol_of_field(name: str) -> str | None:
    head, sep, _rest = name.partition(".")
    return head if sep and head in PROTOCOL_NAMES else None


type ValueMatch = Callable[[Any], bool]


def glob_regex(pattern: str) -> re.Pattern[str]:
    parts = []
    previous_star = False
    for char in pattern:
        if char == "*":
            if not previous_star:
                parts.append(".*")
            previous_star = True
            continue
        previous_star = False
        if char == "?":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    return re.compile("".join(parts), re.IGNORECASE | re.DOTALL)


def _never(_row: Row) -> bool:
    return False


def _always(_row: Row) -> bool:
    return True


def _eq_match(numeric: bool, operand: Scalar) -> ValueMatch:
    if numeric:
        wanted = _as_int(operand)
        if wanted is None:
            return lambda _value: False
        return lambda value: _as_int(value) == wanted
    text = str(operand).casefold()
    return lambda value: str(value).casefold() == text


def _in_match(numeric: bool, operands: Sequence[Scalar]) -> ValueMatch:
    if numeric:
        numbers = {n for n in (_as_int(item) for item in operands) if n is not None}
        return lambda value: _as_int(value) in numbers
    texts = {str(item).casefold() for item in operands}
    return lambda value: str(value).casefold() in texts


def _cidr_match(operand: Scalar) -> ValueMatch:
    try:
        network = ipaddress.ip_network(str(operand), strict=False)
    except ValueError:
        return lambda _value: False

    def matches(value: Any) -> bool:
        try:
            address = ipaddress.ip_address(str(value))
        except ValueError:
            return False
        return address.version == network.version and address in network

    return matches


def _range_match(low: int | None, high: int | None) -> ValueMatch:
    def matches(value: Any) -> bool:
        number = _as_int(value)
        if number is None:
            return False
        if low is not None and number < low:
            return False
        return not (high is not None and number > high)

    return matches


def _is_present(value: Any) -> bool:
    if isinstance(value, str):
        return value != ""
    return value is not None


def _between_match(operands: Sequence[Scalar]) -> ValueMatch | None:
    bounds = [_as_int(item) for item in operands]
    if len(bounds) != 2 or bounds[0] is None or bounds[1] is None:
        return None
    low, high = sorted((bounds[0], bounds[1]))
    return _range_match(low, high)


def _single_match(op: FilterOp, numeric: bool, operand: Scalar) -> ValueMatch | None:
    if op == "eq":
        return _eq_match(numeric, operand)
    if op == "glob":
        pattern = glob_regex(str(operand))
        return lambda value: pattern.fullmatch(str(value)) is not None
    if op == "cidr":
        return _cidr_match(operand)
    bound = _as_int(operand)
    if bound is None:
        return None
    return _range_match(bound, None) if op == "gte" else _range_match(None, bound)


def value_match(definition: FieldDef, cond: FilterCond) -> ValueMatch | None:
    numeric = definition.type in NUMERIC_TYPES
    operands = condition_values(cond)
    if cond.op == "exists":
        return _is_present
    if cond.op == "in":
        return _in_match(numeric, operands)
    if cond.op == "between":
        return _between_match(operands)
    if not operands:
        return None
    return _single_match(cond.op, numeric, operands[0])


def _compile_condition(cond: FilterCond, ctx: CompileContext) -> Predicate:
    definition = FIELD_DEFS_BY_NAME.get(cond.field)
    if definition is None:
        return _never
    matches = value_match(definition, cond)
    if matches is None:
        return _never
    getter = value_getter(cond.field, ctx)

    def predicate(row: Row) -> bool:
        return any(matches(value) for value in getter(row))

    protocol = protocol_of_field(cond.field)
    if protocol is None:
        return predicate

    def with_protocol(row: Row) -> bool:
        return row.protocol == protocol and predicate(row)

    return with_protocol


def _compile_all(node: FilterAll, ctx: CompileContext) -> Predicate:
    parts = [_compile(child, ctx) for child in node.all]
    if not parts:
        return _always
    if len(parts) == 1:
        return parts[0]

    def all_of(row: Row) -> bool:
        return all(part(row) for part in parts)

    return all_of


def _compile_any(node: FilterAny, ctx: CompileContext) -> Predicate:
    options = [_compile(child, ctx) for child in node.any]
    if not options:
        return _never
    if len(options) == 1:
        return options[0]

    def any_of(row: Row) -> bool:
        return any(option(row) for option in options)

    return any_of


def _compile_not(node: FilterNot, ctx: CompileContext) -> Predicate:
    inner = _compile(node.not_, ctx)

    def negated(row: Row) -> bool:
        return not inner(row)

    return negated


def _compile(node: FilterNode, ctx: CompileContext) -> Predicate:
    if isinstance(node, FilterAll):
        return _compile_all(node, ctx)
    if isinstance(node, FilterAny):
        return _compile_any(node, ctx)
    if isinstance(node, FilterNot):
        return _compile_not(node, ctx)
    return _compile_condition(node, ctx)


def compile_filter(node: FilterNode, ctx: CompileContext | None = None) -> Predicate:
    return _compile(node, ctx or CompileContext())


def compile_for_world(node: FilterNode, world: World) -> Predicate:
    return compile_filter(node, context_for_world(world))
