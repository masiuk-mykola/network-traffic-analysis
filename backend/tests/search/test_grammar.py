import pytest

from capture_api.domain.models import FilterAll, FilterAny, FilterCond, FilterNot
from capture_api.errors import DomainError
from capture_api.search.grammar import (
    FilterRow,
    escape_value,
    parse_filter,
    parse_row,
    serialize_row,
    split_values,
)


def test_parses_field_operator_and_values() -> None:
    row = parse_row("dst.port:between:1,1024")
    assert row == FilterRow(field="dst.port", op="between", values=("1", "1024"))


def test_negation_marks_the_row() -> None:
    row = parse_row("src.ip:!eq:10.20.9.250")
    assert row.negated
    assert row.op == "eq"
    assert row.values == ("10.20.9.250",)


def test_only_the_first_two_colons_split_so_ipv6_survives() -> None:
    row = parse_row("src.ip:eq:2001:db8:20:4::5")
    assert row.values == ("2001:db8:20:4::5",)


def test_exists_takes_no_values() -> None:
    row = parse_row("tls.sni:exists:")
    assert row.values == ()
    assert isinstance(parse_filter(["tls.sni:exists:"]), FilterAll)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a,b", ("a", "b")),
        (r"a\,b", ("a,b",)),
        (r"a\\b", ("a\\b",)),
        (r"\\Invoices\\2026\\*", ("\\Invoices\\2026\\*",)),
        ("", ()),
        ("a,,b", ("a", "", "b")),
    ],
)
def test_value_escaping(raw: str, expected: tuple[str, ...]) -> None:
    assert split_values(raw) == expected


def test_escape_round_trips_every_value() -> None:
    values = ("a,b", "back\\slash", r"\Invoices\2026\Q3, final.pdf", "plain")
    encoded = ",".join(escape_value(value) for value in values)
    assert split_values(encoded) == values


def test_serialize_round_trips_a_row() -> None:
    row = FilterRow(field="smb2.path", op="glob", values=(r"\Invoices\2026\*",), negated=True)
    text = serialize_row(row)
    assert text == "smb2.path:!glob:" + "\\\\Invoices\\\\2026\\\\*"
    assert parse_row(text) == row


def test_single_value_becomes_a_plain_condition() -> None:
    node = parse_filter(["protocol:eq:tls"])
    assert isinstance(node, FilterAll)
    assert node.all[0] == FilterCond(field="protocol", op="eq", value="tls")


def test_several_eq_values_become_in() -> None:
    node = parse_filter(["protocol:eq:tls,dns"])
    assert isinstance(node, FilterAll)
    cond = node.all[0]
    assert isinstance(cond, FilterCond)
    assert cond.op == "in"
    assert cond.values == ["tls", "dns"]


def test_several_values_of_another_operator_become_any() -> None:
    node = parse_filter(["tls.sni:glob:*.test,*.invalid"])
    assert isinstance(node, FilterAll)
    assert isinstance(node.all[0], FilterAny)


def test_between_keeps_both_values_in_one_condition() -> None:
    node = parse_filter(["risk.score:between:40,69"])
    assert isinstance(node, FilterAll)
    cond = node.all[0]
    assert isinstance(cond, FilterCond)
    assert cond.values == ["40", "69"]


def test_negated_row_is_wrapped_in_not() -> None:
    node = parse_filter(["src.ip:!cidr:10.20.4.0/23"])
    assert isinstance(node, FilterAll)
    assert isinstance(node.all[0], FilterNot)


def test_rows_are_anded_in_order() -> None:
    node = parse_filter(["protocol:eq:dns", "dns.rcode:eq:NXDOMAIN"])
    assert isinstance(node, FilterAll)
    assert len(node.all) == 2


def test_no_rows_match_everything() -> None:
    node = parse_filter([])
    assert isinstance(node, FilterAll)
    assert node.all == []


@pytest.mark.parametrize("raw", ["protocol", "protocol:eq", ":eq:tls"])
def test_unparseable_rows_are_400_bad_filter_param(raw: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_row(raw, 3)
    assert caught.value.status == 400
    assert caught.value.code == "bad_filter_param"
    assert caught.value.extra["row_index"] == 3


def test_unknown_field_is_422_with_the_row_index() -> None:
    with pytest.raises(DomainError) as caught:
        parse_filter(["protocol:eq:dns", "nope:eq:1"])
    assert caught.value.status == 422
    assert caught.value.code == "unknown_field"
    assert caught.value.extra["row_index"] == 1


def test_operator_not_in_the_catalogue_is_422() -> None:
    with pytest.raises(DomainError) as caught:
        parse_filter(["protocol:glob:t*"])
    assert caught.value.code == "operator_not_allowed"
    assert caught.value.extra["row_index"] == 0


def test_unknown_operator_name_is_422() -> None:
    with pytest.raises(DomainError) as caught:
        parse_row("protocol:matches:tls", 0)
    assert caught.value.code == "operator_not_allowed"


@pytest.mark.parametrize(
    "raw",
    [
        "src.ip:eq:not-an-address",
        "src.ip:cidr:10.20.0.0/99",
        "dst.port:gte:many",
        "protocol:eq:carrier-pigeon",
        "tls.ja3:eq:zzz",
        "risk.score:between:1",
        "tls.sni:exists:something",
    ],
)
def test_bad_values_are_422_bad_value(raw: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_filter([raw])
    assert caught.value.status == 422
    assert caught.value.code == "bad_value"
    assert caught.value.extra["row_index"] == 0


def test_enum_values_are_matched_case_insensitively() -> None:
    node = parse_filter(["dns.rcode:eq:nxdomain"])
    assert isinstance(node, FilterAll)


def test_import_sensor_ids_are_not_rejected_by_the_builtin_enum() -> None:
    node = parse_filter(["sensor:eq:imp-1"])
    assert isinstance(node, FilterAll)
