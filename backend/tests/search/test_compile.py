from collections.abc import Callable

import pytest

from capture_api.domain.models import FilterAll, FilterAny, FilterCond, FilterNode, FilterNot
from capture_api.errors import DomainError
from capture_api.search.compile import (
    CompileContext,
    compile_filter,
    protocol_of_field,
    validate_filter,
)
from capture_api.world.types import Row

RowFactory = Callable[..., Row]


def matches(node: FilterNode, row: Row, ctx: CompileContext | None = None) -> bool:
    return compile_filter(node, ctx)(row)


def cond(
    field: str, op: str, value: object = None, values: list[object] | None = None
) -> FilterCond:
    return FilterCond.model_validate(
        {
            k: v
            for k, v in {"field": field, "op": op, "value": value, "values": values}.items()
            if v is not None
        }
    )


def test_eq_on_a_row_column(make_row: RowFactory) -> None:
    row = make_row(protocol="tls")
    assert matches(cond("protocol", "eq", "tls"), row)
    assert not matches(cond("protocol", "eq", "dns"), row)


def test_eq_is_case_insensitive_for_hostnames(make_row: RowFactory) -> None:
    row = make_row(protocol="tls", attrs={"tls.sni": "docs.example.org"})
    assert matches(cond("tls.sni", "eq", "DOCS.Example.ORG"), row)


def test_eq_on_a_numeric_field_accepts_a_numeric_string(make_row: RowFactory) -> None:
    row = make_row(dst_port=443)
    assert matches(cond("dst.port", "eq", "443"), row)
    assert matches(cond("dst.port", "eq", 443), row)


def test_in_matches_any_value(make_row: RowFactory) -> None:
    row = make_row(protocol="smtp")
    assert matches(cond("protocol", "in", values=["dns", "smtp"]), row)
    assert not matches(cond("protocol", "in", values=["dns", "tls"]), row)


def test_glob_supports_star_and_question_mark(make_row: RowFactory) -> None:
    row = make_row(attrs={"dns.query.name": "static.example.com"})
    assert matches(cond("dns.query.name", "glob", "*.example.com"), row)
    assert matches(cond("dns.query.name", "glob", "static.example.co?"), row)
    assert not matches(cond("dns.query.name", "glob", "*.example.net"), row)


def test_glob_matches_the_whole_value(make_row: RowFactory) -> None:
    row = make_row(attrs={"dns.query.name": "static.example.com"})
    assert not matches(cond("dns.query.name", "glob", "example"), row)


def test_glob_is_case_insensitive_and_treats_backslash_literally(make_row: RowFactory) -> None:
    row = make_row(protocol="smb2", attrs={"smb2.path": (r"\Invoices\2026\Q3.pdf",)})
    assert matches(cond("smb2.path", "glob", r"\invoices\2026\*"), row)
    assert not matches(cond("smb2.path", "glob", r"\Reports\*"), row)


def test_cidr_ipv4(make_row: RowFactory) -> None:
    row = make_row(src_ip="10.20.4.17")
    assert matches(cond("src.ip", "cidr", "10.20.4.0/23"), row)
    assert not matches(cond("src.ip", "cidr", "10.20.8.0/24"), row)


def test_cidr_ipv6_and_never_across_families(make_row: RowFactory) -> None:
    row = make_row(src_ip="2001:db8:20:4::5")
    assert matches(cond("src.ip", "cidr", "2001:db8:20::/48"), row)
    assert not matches(cond("src.ip", "cidr", "10.20.0.0/16"), row)
    assert not matches(cond("src.ip", "cidr", "2001:db8:20::/48"), make_row(src_ip="10.20.4.17"))


def test_gte_and_lte_are_inclusive(make_row: RowFactory) -> None:
    row = make_row(risk_score=70)
    assert matches(cond("risk.score", "gte", 70), row)
    assert matches(cond("risk.score", "lte", 70), row)
    assert not matches(cond("risk.score", "gte", 71), row)


def test_between_is_inclusive_on_both_ends(make_row: RowFactory) -> None:
    assert matches(cond("risk.score", "between", values=[40, 69]), make_row(risk_score=40))
    assert matches(cond("risk.score", "between", values=[40, 69]), make_row(risk_score=69))
    assert not matches(cond("risk.score", "between", values=[40, 69]), make_row(risk_score=70))


def test_between_accepts_reversed_bounds(make_row: RowFactory) -> None:
    assert matches(cond("bytes.up", "between", values=["2000", "100"]), make_row(bytes_up=500))


def test_exists_is_true_only_for_a_non_empty_value(make_row: RowFactory) -> None:
    present = make_row(protocol="tls", attrs={"tls.sni": "docs.example.org"})
    empty = make_row(protocol="tls", attrs={"tls.sni": ""})
    absent = make_row(protocol="tls")
    assert matches(cond("tls.sni", "exists"), present)
    assert not matches(cond("tls.sni", "exists"), empty)
    assert not matches(cond("tls.sni", "exists"), absent)


def test_duration_and_bytes_read_row_values(make_row: RowFactory) -> None:
    row = make_row(duration_ms=30_000, bytes_up=1_048_576)
    assert matches(cond("duration_ms", "gte", 30_000), row)
    assert matches(cond("bytes.up", "gte", "1048576"), row)


def test_a_tuple_attribute_matches_on_any_element(make_row: RowFactory) -> None:
    row = make_row(
        protocol="smb2",
        attrs={"smb2.path": (r"\Invoices\2026\a.pdf", r"\Invoices\2026\b.pdf")},
    )
    assert matches(cond("smb2.path", "eq", r"\Invoices\2026\b.pdf"), row)


def test_detection_rule_is_a_tuple_attribute(make_row: RowFactory) -> None:
    row = make_row(attrs={"detection.rule": ("port_scan", "rare_user_agent")})
    assert matches(cond("detection.rule", "eq", "rare_user_agent"), row)
    assert matches(cond("detection.rule", "exists"), row)
    assert not matches(cond("detection.rule", "exists"), make_row())


def test_host_matches_either_endpoint(make_row: RowFactory) -> None:
    def hostname(ip: str) -> str | None:
        return {"10.20.4.17": "ws-hq-001.quillmere.example"}.get(ip)

    ctx = CompileContext(hostname=hostname, country=lambda _ip: None)
    row = make_row(src_ip="10.20.4.17", dst_ip="192.0.2.10")
    assert matches(cond("host", "glob", "ws-hq-*"), row, ctx)
    assert not matches(cond("dst.host", "exists"), row, ctx)


def test_dst_country_uses_the_lookup(make_row: RowFactory) -> None:
    ctx = CompileContext(hostname=lambda _ip: None, country=lambda _ip: "PT")
    assert matches(cond("dst.country", "eq", "pt"), make_row(), ctx)


def test_all_any_and_not(make_row: RowFactory) -> None:
    row = make_row(protocol="dns", risk_score=80)
    node = FilterAll(
        all=[
            cond("protocol", "eq", "dns"),
            FilterAny(any=[cond("risk.score", "gte", 70), cond("risk.score", "lte", 10)]),
            FilterNot(not_=cond("dst.port", "eq", 443)),
        ]
    )
    assert matches(node, row)


def test_an_empty_all_matches_everything_and_an_empty_any_nothing(make_row: RowFactory) -> None:
    assert matches(FilterAll(all=[]), make_row())
    assert not matches(FilterAny(any=[]), make_row())


def test_a_protocol_condition_implies_the_protocol(make_row: RowFactory) -> None:
    dns_row = make_row(protocol="dns", attrs={"dns.query.name": "telemetry.cdn.test"})
    tls_row = make_row(protocol="tls", attrs={"dns.query.name": "telemetry.cdn.test"})
    node = cond("dns.query.name", "eq", "telemetry.cdn.test")
    assert matches(node, dns_row)
    assert not matches(node, tls_row)


def test_not_of_a_protocol_condition_matches_other_protocols(make_row: RowFactory) -> None:
    node = FilterNot(not_=cond("tls.sni", "glob", "*.test"))
    assert matches(node, make_row(protocol="dns"))
    assert matches(node, make_row(protocol="tls", attrs={"tls.sni": "docs.example.org"}))
    assert not matches(node, make_row(protocol="tls", attrs={"tls.sni": "telemetry.cdn.test"}))


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("tls.sni", "tls"),
        ("smtp.attachment.sha256", "smtp"),
        ("dst.country", None),
        ("risk.score", None),
        ("protocol", None),
    ],
)
def test_protocol_of_field(field: str, expected: str | None) -> None:
    assert protocol_of_field(field) == expected


def test_validate_filter_reports_the_wire_location() -> None:
    node = FilterAll(all=[FilterNot(not_=cond("nope", "eq", "x"))])
    with pytest.raises(DomainError) as caught:
        validate_filter(node)
    assert caught.value.status == 422
    assert caught.value.code == "unknown_field"
    assert caught.value.extra["loc"] == ["body", "filter", "all", 0, "not"]


def test_validate_filter_rejects_an_operator_the_field_does_not_allow() -> None:
    with pytest.raises(DomainError) as caught:
        validate_filter(cond("protocol", "glob", "t*"))
    assert caught.value.code == "operator_not_allowed"


def test_validate_filter_accepts_in_wherever_eq_is_allowed() -> None:
    validate_filter(cond("protocol", "in", values=["dns", "tls"]))


def test_validate_filter_rejects_a_bad_value() -> None:
    with pytest.raises(DomainError) as caught:
        validate_filter(cond("src.ip", "eq", "somewhere"))
    assert caught.value.code == "bad_value"
