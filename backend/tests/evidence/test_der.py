from typing import Any

import pytest

from capture_api.world import der

START_MS = 1_761_566_400_000


def parse(data: bytes) -> tuple[int, bytes, bytes]:
    tag = data[0]
    first = data[1]
    if first < 0x80:
        length, offset = first, 2
    else:
        count = first & 0x7F
        length = int.from_bytes(data[2 : 2 + count], "big")
        offset = 2 + count
    return tag, data[offset : offset + length], data[offset + length :]


def children(body: bytes) -> list[tuple[int, bytes]]:
    out: list[tuple[int, bytes]] = []
    rest = body
    while rest:
        tag, inner, rest = parse(rest)
        out.append((tag, inner))
    return out


def walk(tag: int, body: bytes) -> list[Any]:
    out: list[Any] = [(tag, body)]
    if tag & 0x20 or tag == der.TAG_OCTET_STRING:
        try:
            inner = children(body)
        except IndexError:
            return out
        for child_tag, child_body in inner:
            out.extend(walk(child_tag, child_body))
    return out


def spec(**overrides: Any) -> der.CertificateSpec:
    base: dict[str, Any] = {
        "subject_cn": "a1b2.invalid",
        "issuer_cn": "a1b2.invalid",
        "serial": 0x0A1B2C3D4E5F6071,
        "not_before_ms": START_MS - 86_400_000,
        "not_after_ms": START_MS + 7 * 86_400_000,
        "modulus": bytes(range(256)),
        "signature": bytes(256),
        "san_dns": ("telemetry.cdn-metrics.test",),
    }
    base.update(overrides)
    return der.CertificateSpec(**base)


def test_length_encoding() -> None:
    assert der.tlv(0x04, b"x")[:2] == b"\x04\x01"
    assert der.tlv(0x04, b"y" * 200)[:3] == b"\x04\x81\xc8"
    assert der.tlv(0x04, b"y" * 400)[:4] == b"\x04\x82\x01\x90"


def test_integer_adds_a_sign_byte() -> None:
    assert der.integer(0) == b"\x02\x01\x00"
    assert der.integer(127) == b"\x02\x01\x7f"
    assert der.integer(128) == b"\x02\x02\x00\x80"
    assert der.integer_bytes(b"\x00\x00\xff") == b"\x02\x02\x00\xff"


def test_negative_integers_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        der.integer(-1)


def test_object_identifier() -> None:
    sha256_rsa = bytes.fromhex("06092a864886f70d01010b")
    assert der.object_identifier(der.OID_SHA256_WITH_RSA) == sha256_rsa
    assert der.object_identifier(der.OID_COMMON_NAME) == bytes.fromhex("0603550403")
    with pytest.raises(ValueError, match="two arcs"):
        der.object_identifier((2,))


def test_utc_time_format() -> None:
    _, body, rest = parse(der.utc_time(1_762_164_000_000))
    assert body == b"251103100000Z"
    assert rest == b""


def test_certificate_is_well_formed() -> None:
    data = der.certificate_der(spec())
    tag, body, rest = parse(data)
    assert tag == der.TAG_SEQUENCE
    assert rest == b""
    parts = children(body)
    assert len(parts) == 3
    tbs_tag, tbs = parts[0]
    assert tbs_tag == der.TAG_SEQUENCE
    assert parts[2][0] == der.TAG_BIT_STRING
    fields = children(tbs)
    assert fields[0][0] == 0xA0
    assert fields[0][1] == der.integer(2)
    assert fields[1] == (der.TAG_INTEGER, bytes.fromhex("0a1b2c3d4e5f6071"))


def test_certificate_carries_the_names_dates_and_san() -> None:
    data = der.certificate_der(spec(subject_cn="leaf.invalid", issuer_cn="Example Trust CA"))
    tag, body, _ = parse(data)
    nodes = walk(tag, body)
    strings = {value for node_tag, value in nodes if node_tag == der.TAG_UTF8_STRING}
    assert b"leaf.invalid" in strings
    assert b"Example Trust CA" in strings
    times = {value for node_tag, value in nodes if node_tag == der.TAG_UTC_TIME}
    assert len(times) == 2
    san = {value for node_tag, value in nodes if node_tag == 0x82}
    assert b"telemetry.cdn-metrics.test" in san


def test_certificate_bytes_are_deterministic() -> None:
    assert der.certificate_der(spec()) == der.certificate_der(spec())
    assert der.certificate_der(spec()) != der.certificate_der(spec(serial=2))


def test_self_signed_flag() -> None:
    assert spec().self_signed is True
    assert spec(issuer_cn="Example Trust CA").self_signed is False
