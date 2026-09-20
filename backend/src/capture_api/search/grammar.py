from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from capture_api.domain.base import Scalar
from capture_api.domain.models import (
    FilterAll,
    FilterAny,
    FilterCond,
    FilterNode,
    FilterNot,
    FilterOp,
)
from capture_api.errors import DomainError
from capture_api.search.compile import FilterError, validate_condition

OPERATORS: Mapping[str, FilterOp] = {
    "eq": "eq",
    "in": "in",
    "cidr": "cidr",
    "glob": "glob",
    "gte": "gte",
    "lte": "lte",
    "between": "between",
    "exists": "exists",
}
"""Every operator name the grammar accepts (the :data:`FilterOp` literals)."""

NEGATION = "!"
SEPARATOR = ":"
VALUE_SEPARATOR = ","
ESCAPE = "\\"


@dataclass(frozen=True, slots=True)
class FilterRow:
    field: str
    op: FilterOp
    values: tuple[str, ...]
    negated: bool = False


def _bad_param(row_index: int, detail: str) -> DomainError:
    return DomainError(400, "bad_filter_param", detail, extra={"row_index": row_index})


def _semantic(row_index: int, code: str, detail: str) -> DomainError:
    return DomainError(422, code, detail, extra={"row_index": row_index})


def split_values(raw: str) -> tuple[str, ...]:
    if raw == "":
        return ()
    values: list[str] = []
    current: list[str] = []
    escaped = False
    for char in raw:
        if escaped:
            if char not in (VALUE_SEPARATOR, ESCAPE):
                current.append(ESCAPE)
            current.append(char)
            escaped = False
        elif char == ESCAPE:
            escaped = True
        elif char == VALUE_SEPARATOR:
            values.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append(ESCAPE)
    values.append("".join(current))
    return tuple(values)


def escape_value(value: str) -> str:
    return value.replace(ESCAPE, ESCAPE * 2).replace(VALUE_SEPARATOR, ESCAPE + VALUE_SEPARATOR)


def serialize_row(row: FilterRow) -> str:
    op = f"{NEGATION if row.negated else ''}{row.op}"
    values = VALUE_SEPARATOR.join(escape_value(value) for value in row.values)
    return f"{row.field}{SEPARATOR}{op}{SEPARATOR}{values}"


def serialize_rows(rows: Sequence[FilterRow]) -> list[str]:
    return [serialize_row(row) for row in rows]


def parse_row(raw: str, row_index: int = 0) -> FilterRow:
    field, found_field, rest = raw.partition(SEPARATOR)
    op_token, found_op, values = rest.partition(SEPARATOR)
    if not found_field or not found_op:
        raise _bad_param(
            row_index, f"'{raw}' is not a filter row; expected '<field>:<op>:<values>'."
        )
    if not field:
        raise _bad_param(row_index, "A filter row must start with a field name.")
    negated = op_token.startswith(NEGATION)
    op_name = op_token[1:] if negated else op_token
    op = OPERATORS.get(op_name.casefold())
    if op is None:
        raise _semantic(row_index, "operator_not_allowed", f"'{op_name}' is not a filter operator.")
    return FilterRow(field=field, op=op, values=split_values(values), negated=negated)


def row_to_node(row: FilterRow, row_index: int = 0) -> FilterNode:
    node = _condition(row, row_index)
    return FilterNot(not_=node) if row.negated else node


def _condition(row: FilterRow, row_index: int) -> FilterNode:
    values: list[Scalar] = list(row.values)
    try:
        if row.op == "exists":
            if values not in ([], [""]):
                raise _semantic(
                    row_index, "bad_value", "'exists' takes no values ('tls.sni:exists:')."
                )
            cond = FilterCond(field=row.field, op="exists")
        elif row.op in ("in", "between"):
            cond = FilterCond(field=row.field, op=row.op, values=values)
        elif len(values) == 1:
            cond = FilterCond(field=row.field, op=row.op, value=values[0])
        elif row.op == "eq":
            cond = FilterCond(field=row.field, op="in", values=values)
        else:
            return _any_of(row, values, row_index)
    except ValidationError as exc:
        raise _semantic(row_index, "bad_value", _first_message(exc)) from exc
    _validate(cond, row_index)
    return cond


def _any_of(row: FilterRow, values: Sequence[Scalar], row_index: int) -> FilterNode:
    if not values:
        raise _semantic(row_index, "bad_value", f"'{row.op}' needs a value.")
    conditions: list[FilterNode] = []
    for value in values:
        try:
            cond = FilterCond(field=row.field, op=row.op, value=value)
        except ValidationError as exc:
            raise _semantic(row_index, "bad_value", _first_message(exc)) from exc
        _validate(cond, row_index)
        conditions.append(cond)
    return FilterAny(any=conditions)


def _validate(cond: FilterCond, row_index: int) -> None:
    try:
        validate_condition(cond)
    except FilterError as exc:
        raise _semantic(row_index, exc.code, exc.detail) from exc


def _first_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:  # pragma: no cover - pydantic always reports at least one
        return "Invalid filter row."
    return str(errors[0].get("msg", "Invalid filter row.")).removeprefix("Value error, ")


def parse_filter(raw_rows: Sequence[str]) -> FilterNode:
    return FilterAll(all=[node_for(raw, index) for index, raw in enumerate(raw_rows)])


def node_for(raw: str, row_index: int) -> FilterNode:
    return row_to_node(parse_row(raw, row_index), row_index)
