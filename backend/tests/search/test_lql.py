import pytest

from capture_api.domain.models import FilterAll, FilterAny, FilterCond, FilterNot
from capture_api.search.lql import LqlError, parse

CORPUS: list[tuple[str, str]] = [
    ("protocol = tls", "protocol = tls"),
    ("PROTOCOL = tls AND dst.port = 443", "protocol = tls and dst.port = 443"),
    ("protocol = tls dst.port = 443", "protocol = tls and dst.port = 443"),
    ("protocol = dns or protocol = tls", "protocol = dns or protocol = tls"),
    ("not protocol = ntp", "not (protocol = ntp)"),
    ("has tls.sni", "has tls.sni"),
    ("tls.sni ~ *.example.net", "tls.sni ~ *.example.net"),
    ("src.ip cidr 10.20.4.0/23", "src.ip cidr 10.20.4.0/23"),
    ("risk.score >= 70", "risk.score >= 70"),
    ("dst.port <= 1024", "dst.port <= 1024"),
    ("protocol in (dns, tls)", "protocol in (dns, tls)"),
    ("bytes.up between 1000 .. 2000", "bytes.up between 1000 .. 2000"),
    ("bytes.up between 1000..2000", "bytes.up between 1000 .. 2000"),
    ("src.ip = 2001:db8:20:4::5", "src.ip = 2001:db8:20:4::5"),
    (r"smb2.path ~ \Invoices\2026\*", r"smb2.path ~ \Invoices\2026\*"),
    (
        'smtp.mail_from = "billing@quillmere-frieght.example"',
        'smtp.mail_from = "billing@quillmere-frieght.example"',
    ),
    (
        "protocol = tls and (tls.sni ~ *.test or risk.score >= 70)",
        "protocol = tls and (tls.sni ~ *.test or risk.score >= 70)",
    ),
    (
        "protocol = tls or dst.port = 443 and risk.score >= 70",
        "protocol = tls or dst.port = 443 and risk.score >= 70",
    ),
]


@pytest.mark.parametrize(("source", "expected"), CORPUS)
def test_normalized_form(source: str, expected: str) -> None:
    _node, normalized = parse(source)
    assert normalized == expected


@pytest.mark.parametrize(("source", "_expected"), CORPUS)
def test_normalized_form_round_trips(source: str, _expected: str) -> None:
    node, normalized = parse(source)
    again, normalized_again = parse(normalized)
    assert again == node
    assert normalized_again == normalized


def test_not_equal_becomes_not_of_eq() -> None:
    node, normalized = parse("protocol != ntp")
    assert node == FilterNot(not_=FilterCond(field="protocol", op="eq", value="ntp"))
    assert normalized == "not (protocol = ntp)"


def test_juxtaposition_is_and() -> None:
    node, _ = parse("protocol = dns dns.rcode = NXDOMAIN")
    assert isinstance(node, FilterAll)
    assert len(node.all) == 2


def test_or_binds_looser_than_and() -> None:
    node, _ = parse("protocol = dns and dst.port = 53 or protocol = tls")
    assert isinstance(node, FilterAny)
    assert isinstance(node.any[0], FilterAll)


def test_quotes_are_added_only_where_needed() -> None:
    _node, normalized = parse('smtp.mail_from = "a b"')
    assert normalized == 'smtp.mail_from = "a b"'


def test_quoted_escapes() -> None:
    node, _ = parse(r'http.user_agent = "say \"hi\""')
    assert isinstance(node, FilterCond)
    assert node.value == 'say "hi"'


def test_an_empty_query_matches_everything() -> None:
    node, normalized = parse("   ")
    assert node == FilterAll(all=[])
    assert normalized == ""


def test_keywords_are_case_insensitive() -> None:
    node, _ = parse("HAS tls.sni AND NOT protocol = ntp")
    assert isinstance(node, FilterAll)


@pytest.mark.parametrize(
    ("source", "pos", "end"),
    [
        ("protocol", 8, 9),
        ("protocol =", 10, 11),
        ("protocol = tls and", 18, 19),
        ("(protocol = tls", 15, 16),
        ("protocol = tls)", 14, 15),
        ('protocol = "tls', 11, 15),
        ("protocol = tls !", 15, 16),
    ],
)
def test_syntax_errors_report_their_span(source: str, pos: int, end: int) -> None:
    with pytest.raises(LqlError) as caught:
        parse(source)
    assert (caught.value.pos, caught.value.end) == (pos, end)


def test_an_unknown_field_is_reported_at_the_condition() -> None:
    with pytest.raises(LqlError) as caught:
        parse("nope = 1")
    assert caught.value.pos == 0
    assert caught.value.end == 8
    assert "nope" in caught.value.detail


def test_a_bad_value_is_reported_at_the_condition() -> None:
    with pytest.raises(LqlError) as caught:
        parse("src.ip = somewhere")
    assert (caught.value.pos, caught.value.end) == (0, 18)


def test_the_error_renders_as_422_lql_syntax() -> None:
    with pytest.raises(LqlError) as caught:
        parse("protocol")
    error = caught.value.as_domain_error()
    assert error.status == 422
    assert error.code == "lql_syntax"
    assert error.extra["ctx"] == {"pos": 8, "end": 9}
