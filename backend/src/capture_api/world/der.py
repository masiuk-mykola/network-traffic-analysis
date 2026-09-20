from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

TAG_BOOLEAN = 0x01
TAG_INTEGER = 0x02
TAG_BIT_STRING = 0x03
TAG_OCTET_STRING = 0x04
TAG_NULL = 0x05
TAG_OID = 0x06
TAG_UTF8_STRING = 0x0C
TAG_PRINTABLE_STRING = 0x13
TAG_IA5_STRING = 0x16
TAG_UTC_TIME = 0x17
TAG_SEQUENCE = 0x30
TAG_SET = 0x31

type Oid = tuple[int, ...]
"""An object identifier as its arcs (``(2, 5, 4, 3)`` is ``id-at-commonName``)."""

OID_COMMON_NAME: Oid = (2, 5, 4, 3)
OID_ORGANISATION: Oid = (2, 5, 4, 10)
OID_COUNTRY: Oid = (2, 5, 4, 6)
OID_RSA_ENCRYPTION: Oid = (1, 2, 840, 113549, 1, 1, 1)
OID_SHA256_WITH_RSA: Oid = (1, 2, 840, 113549, 1, 1, 11)
OID_BASIC_CONSTRAINTS: Oid = (2, 5, 29, 19)
OID_KEY_USAGE: Oid = (2, 5, 29, 15)
OID_SUBJECT_ALT_NAME: Oid = (2, 5, 29, 17)
OID_EXTENDED_KEY_USAGE: Oid = (2, 5, 29, 37)
OID_SERVER_AUTH: Oid = (1, 3, 6, 1, 5, 5, 7, 3, 1)


def _length(size: int) -> bytes:
    if size < 0x80:
        return bytes((size,))
    body = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes((0x80 | len(body),)) + body


def tlv(tag: int, body: bytes) -> bytes:
    return bytes((tag,)) + _length(len(body)) + body


def integer(value: int) -> bytes:
    if value < 0:
        raise ValueError("only non-negative integers are supported")
    if value == 0:
        return tlv(TAG_INTEGER, b"\x00")
    return tlv(TAG_INTEGER, value.to_bytes((value.bit_length() + 8) // 8, "big"))


def integer_bytes(raw: bytes) -> bytes:
    body = raw.lstrip(b"\x00") or b"\x00"
    if body[0] & 0x80:
        body = b"\x00" + body
    return tlv(TAG_INTEGER, body)


def boolean(value: bool) -> bytes:
    return tlv(TAG_BOOLEAN, b"\xff" if value else b"\x00")


def null() -> bytes:
    return tlv(TAG_NULL, b"")


def octet_string(data: bytes) -> bytes:
    return tlv(TAG_OCTET_STRING, data)


def bit_string(data: bytes, unused_bits: int = 0) -> bytes:
    return tlv(TAG_BIT_STRING, bytes((unused_bits,)) + data)


def object_identifier(arcs: Sequence[int]) -> bytes:
    parts = list(arcs)
    if len(parts) < 2:
        raise ValueError("an OID needs at least two arcs")
    body = bytearray((parts[0] * 40 + parts[1],))
    for arc in parts[2:]:
        chunk = bytearray((arc & 0x7F,))
        rest = arc >> 7
        while rest:
            chunk.append((rest & 0x7F) | 0x80)
            rest >>= 7
        body.extend(reversed(chunk))
    return tlv(TAG_OID, bytes(body))


def utf8_string(text: str) -> bytes:
    return tlv(TAG_UTF8_STRING, text.encode())


def printable_string(text: str) -> bytes:
    return tlv(TAG_PRINTABLE_STRING, text.encode("ascii"))


def ia5_string(text: str) -> bytes:
    return tlv(TAG_IA5_STRING, text.encode("ascii", "replace"))


def sequence(*parts: bytes) -> bytes:
    return tlv(TAG_SEQUENCE, b"".join(parts))


def set_of(*parts: bytes) -> bytes:
    return tlv(TAG_SET, b"".join(parts))


def explicit(number: int, body: bytes) -> bytes:
    return tlv(0xA0 | number, body)


def context_primitive(number: int, body: bytes) -> bytes:
    return tlv(0x80 | number, body)


def utc_time(ms: int) -> bytes:
    moment = datetime.fromtimestamp(ms // 1000, UTC)
    return tlv(TAG_UTC_TIME, moment.strftime("%y%m%d%H%M%SZ").encode("ascii"))


def algorithm_identifier(oid: Oid) -> bytes:
    return sequence(object_identifier(oid), null())


def relative_name(oid: Oid, value: str) -> bytes:
    return set_of(sequence(object_identifier(oid), utf8_string(value)))


def distinguished_name(common_name: str, organisation: str | None, country: str | None) -> bytes:
    parts = []
    if country:
        parts.append(relative_name(OID_COUNTRY, country))
    if organisation:
        parts.append(relative_name(OID_ORGANISATION, organisation))
    parts.append(relative_name(OID_COMMON_NAME, common_name))
    return sequence(*parts)


def _extension(oid: Oid, body: bytes, *, critical: bool = False) -> bytes:
    parts = [object_identifier(oid)]
    if critical:
        parts.append(boolean(True))
    parts.append(octet_string(body))
    return sequence(*parts)


@dataclass(frozen=True, slots=True)
class CertificateSpec:
    subject_cn: str
    issuer_cn: str
    serial: int
    not_before_ms: int
    not_after_ms: int
    modulus: bytes
    """Big-endian "RSA modulus": seeded filler, 256 bytes in practice."""
    signature: bytes
    """Dummy signature bytes."""
    subject_org: str | None = None
    issuer_org: str | None = None
    country: str | None = None
    san_dns: Sequence[str] = field(default_factory=tuple)
    is_ca: bool = False

    @property
    def self_signed(self) -> bool:
        return self.subject_cn == self.issuer_cn


def subject_public_key_info(modulus: bytes, exponent: int = 65537) -> bytes:
    key = sequence(integer_bytes(modulus), integer(exponent))
    return sequence(algorithm_identifier(OID_RSA_ENCRYPTION), bit_string(key))


def _extensions(spec: CertificateSpec) -> bytes:
    items = [
        _extension(
            OID_BASIC_CONSTRAINTS,
            sequence(boolean(True)) if spec.is_ca else sequence(),
            critical=True,
        ),
        _extension(OID_KEY_USAGE, bit_string(b"\xa0", 5), critical=True),
    ]
    if not spec.is_ca:
        items.append(
            _extension(OID_EXTENDED_KEY_USAGE, sequence(object_identifier(OID_SERVER_AUTH)))
        )
    if spec.san_dns:
        names = [context_primitive(2, name.encode("ascii", "replace")) for name in spec.san_dns]
        items.append(_extension(OID_SUBJECT_ALT_NAME, sequence(*names)))
    return explicit(3, sequence(*items))


def certificate_der(spec: CertificateSpec) -> bytes:
    tbs = sequence(
        explicit(0, integer(2)),
        integer(spec.serial),
        algorithm_identifier(OID_SHA256_WITH_RSA),
        distinguished_name(spec.issuer_cn, spec.issuer_org, spec.country),
        sequence(utc_time(spec.not_before_ms), utc_time(spec.not_after_ms)),
        distinguished_name(spec.subject_cn, spec.subject_org, spec.country),
        subject_public_key_info(spec.modulus),
        _extensions(spec),
    )
    return sequence(tbs, algorithm_identifier(OID_SHA256_WITH_RSA), bit_string(spec.signature))
