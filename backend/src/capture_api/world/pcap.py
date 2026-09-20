import hashlib
import ipaddress
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from capture_api.world.ssh_profiles import SshProfile
from capture_api.world.tls_profiles import (
    TLS12,
    TLS13,
    TlsClientProfile,
    TlsServerProfile,
)
from capture_api.world.types import Row

MAX_PACKETS = 256
"""Hard cap: only the first 256 packets of a session are written."""

SNAPLEN = 65535
LINKTYPE_ETHERNET = 1
MSS = 1460

ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_IPV6 = 0x86DD
PROTO_TCP = 6
PROTO_UDP = 17

FIN = 0x01
SYN = 0x02
RST = 0x04
PSH = 0x08
ACK = 0x10

UP = 0
"""Client → server."""
DOWN = 1
"""Server → client."""

_DNS_TYPE_CODES: Mapping[str, int] = {
    "A": 1,
    "NS": 2,
    "CNAME": 5,
    "SOA": 6,
    "PTR": 12,
    "MX": 15,
    "TXT": 16,
    "AAAA": 28,
    "SRV": 33,
    "HTTPS": 65,
}

_HTTP_REASONS: Mapping[int, str] = {
    200: "OK",
    201: "Created",
    204: "No Content",
    206: "Partial Content",
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


def filler_bytes(label: str, size: int) -> bytes:
    if size <= 0:
        return b""
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.blake2b(f"{label}|{counter}".encode(), digest_size=64).digest()
        counter += 1
    return bytes(out[:size])


@dataclass(frozen=True, slots=True)
class TlsWire:
    client: TlsClientProfile
    server: TlsServerProfile
    sni: str
    certificates: Sequence[bytes] = field(default_factory=tuple)
    label: str = "tls"
    """Seeds the deterministic randoms, session id and key shares."""


@dataclass(frozen=True, slots=True)
class SshWire:
    client: SshProfile
    server: SshProfile


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for index in range(0, len(data), 2):
        total += (data[index] << 8) | data[index + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def mac_for_ip(ip: str) -> bytes:
    return b"\x02\x00" + hashlib.blake2b(ip.encode(), digest_size=4).digest()


def _ethernet(dst: bytes, src: bytes, ethertype: int) -> bytes:
    return dst + src + struct.pack("!H", ethertype)


def _ipv4(src: str, dst: str, proto: int, payload: bytes, *, ident: int, ttl: int) -> bytes:
    total = 20 + len(payload)
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total,
        ident & 0xFFFF,
        0x4000,
        ttl,
        proto,
        0,
        ipaddress.IPv4Address(src).packed,
        ipaddress.IPv4Address(dst).packed,
    )
    checksum = _checksum(header)
    return header[:10] + struct.pack("!H", checksum) + header[12:] + payload


def _ipv6(src: str, dst: str, proto: int, payload: bytes, ttl: int) -> bytes:
    header = struct.pack(
        "!IHBB16s16s",
        0x60000000,
        len(payload),
        proto,
        ttl,
        ipaddress.IPv6Address(src).packed,
        ipaddress.IPv6Address(dst).packed,
    )
    return header + payload


def _pseudo_header(src: str, dst: str, proto: int, length: int) -> bytes:
    if ":" in src:
        return (
            ipaddress.IPv6Address(src).packed
            + ipaddress.IPv6Address(dst).packed
            + struct.pack("!IHBB", length, 0, 0, proto)
        )
    return (
        ipaddress.IPv4Address(src).packed
        + ipaddress.IPv4Address(dst).packed
        + struct.pack("!BBH", 0, proto, length)
    )


def _udp(src: str, dst: str, sport: int, dport: int, payload: bytes) -> bytes:
    length = 8 + len(payload)
    segment = struct.pack("!HHHH", sport, dport, length, 0) + payload
    checksum = _checksum(_pseudo_header(src, dst, PROTO_UDP, length) + segment)
    return segment[:6] + struct.pack("!H", checksum or 0xFFFF) + segment[8:]


def _tcp(
    src: str,
    dst: str,
    sport: int,
    dport: int,
    *,
    seq: int,
    ack: int,
    flags: int,
    window: int,
    payload: bytes,
) -> bytes:
    segment = (
        struct.pack(
            "!HHIIBBHHH",
            sport,
            dport,
            seq & 0xFFFFFFFF,
            ack & 0xFFFFFFFF,
            0x50,
            flags,
            window,
            0,
            0,
        )
        + payload
    )
    checksum = _checksum(_pseudo_header(src, dst, PROTO_TCP, len(segment)) + segment)
    return segment[:16] + struct.pack("!H", checksum) + segment[18:]


class PacketWriter:
    __slots__ = ("_packets", "_ts_us", "step_us")

    def __init__(self, start_us: int, step_us: int = 1000) -> None:
        self._packets: list[tuple[int, bytes]] = []
        self._ts_us = start_us
        self.step_us = max(1, step_us)

    def __len__(self) -> int:
        return len(self._packets)

    @property
    def full(self) -> bool:
        return len(self._packets) >= MAX_PACKETS

    def advance(self, micros: int) -> None:
        self._ts_us += max(0, micros)

    def add(self, frame: bytes) -> bool:
        if self.full:
            return False
        self._packets.append((self._ts_us, frame))
        self._ts_us += self.step_us
        return True

    def to_bytes(self) -> bytes:
        out = bytearray(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, SNAPLEN, LINKTYPE_ETHERNET))
        for ts_us, frame in self._packets:
            size = len(frame)
            out += struct.pack("<IIII", ts_us // 1_000_000, ts_us % 1_000_000, size, size)
            out += frame
        return bytes(out)


class Conversation:
    __slots__ = ("_ident", "_macs", "_seq", "addrs", "ports", "sent", "v6", "writer")

    def __init__(
        self,
        writer: PacketWriter,
        *,
        src_ip: str,
        src_port: int,
        dst_ip: str,
        dst_port: int,
        isn_up: int,
        isn_down: int,
    ) -> None:
        self.writer = writer
        self.addrs = (src_ip, dst_ip)
        self.ports = (src_port, dst_port)
        self.v6 = ":" in src_ip
        self._macs = (mac_for_ip(src_ip), mac_for_ip(dst_ip))
        self._seq = [isn_up & 0xFFFFFFFF, isn_down & 0xFFFFFFFF]
        self._ident = 0x4000
        self.sent = [0, 0]
        """Payload bytes written per direction (``UP``/``DOWN``)."""

    def _frame(self, direction: int, proto: int, payload: bytes) -> bytes:
        src, dst = (self.addrs[0], self.addrs[1]) if direction == UP else self.addrs[::-1]
        smac, dmac = (self._macs[0], self._macs[1]) if direction == UP else self._macs[::-1]
        if self.v6:
            packet = _ipv6(src, dst, proto, payload, 64)
            return _ethernet(dmac, smac, ETHERTYPE_IPV6) + packet
        self._ident = (self._ident + 1) & 0xFFFF
        packet = _ipv4(
            src, dst, proto, payload, ident=self._ident, ttl=64 if direction == UP else 57
        )
        return _ethernet(dmac, smac, ETHERTYPE_IPV4) + packet

    def _endpoints(self, direction: int) -> tuple[str, str, int, int]:
        if direction == UP:
            return self.addrs[0], self.addrs[1], self.ports[0], self.ports[1]
        return self.addrs[1], self.addrs[0], self.ports[1], self.ports[0]

    def datagram(self, direction: int, payload: bytes) -> bool:
        src, dst, sport, dport = self._endpoints(direction)
        datagram = _udp(src, dst, sport, dport, payload)
        written = self.writer.add(self._frame(direction, PROTO_UDP, datagram))
        if written:
            self.sent[direction] += len(payload)
        return written

    def segment(self, direction: int, flags: int, payload: bytes = b"") -> bool:
        src, dst, sport, dport = self._endpoints(direction)
        other = DOWN if direction == UP else UP
        frame = self._frame(
            direction,
            PROTO_TCP,
            _tcp(
                src,
                dst,
                sport,
                dport,
                seq=self._seq[direction],
                ack=self._seq[other] if flags & ACK else 0,
                flags=flags,
                window=64240 if direction == UP else 65535,
                payload=payload,
            ),
        )
        written = self.writer.add(frame)
        if written:
            self._seq[direction] = (
                self._seq[direction] + len(payload) + (1 if flags & (SYN | FIN) else 0)
            ) & 0xFFFFFFFF
            self.sent[direction] += len(payload)
        return written

    def handshake(self) -> bool:
        return self.segment(UP, SYN) and self.segment(DOWN, SYN | ACK) and self.segment(UP, ACK)

    def send(self, direction: int, payload: bytes, *, acknowledge: bool = True) -> bool:
        if not payload:
            return not self.writer.full
        other = DOWN if direction == UP else UP
        for offset in range(0, len(payload), MSS):
            chunk = payload[offset : offset + MSS]
            last = offset + MSS >= len(payload)
            if not self.segment(direction, PSH | ACK if last else ACK, chunk):
                return False
            if acknowledge and not self.segment(other, ACK):
                return False
        return True

    def finish(self) -> None:
        if self.writer.full:
            return
        self.segment(UP, FIN | ACK)
        self.segment(DOWN, FIN | ACK)
        self.segment(UP, ACK)


def encode_dns_name(name: str) -> bytes:
    stripped = name.strip().rstrip(".")
    if not stripped:
        return b"\x00"
    out = bytearray()
    for label in stripped.split("."):
        raw = label.encode("ascii", "replace")[:63]
        out.append(len(raw))
        out += raw
    out.append(0)
    return bytes(out)


def _packed_address(data: str, *, v6: bool) -> bytes:
    try:
        return (ipaddress.IPv6Address if v6 else ipaddress.IPv4Address)(data).packed
    except ValueError:
        return b"\x00" * (16 if v6 else 4)


def _dns_rdata(rtype: int, data: str) -> bytes:
    if rtype in {1, 28}:
        return _packed_address(data, v6=rtype == 28)
    if rtype == 15:
        return struct.pack("!H", 10) + encode_dns_name(data)
    if rtype == 16:
        raw = data.encode()[:255]
        return bytes((len(raw),)) + raw
    if rtype == 33:
        return struct.pack("!HHH", 10, 0, 443) + encode_dns_name(data)
    if rtype == 65:
        return struct.pack("!H", 1) + b"\x00"
    return encode_dns_name(data)


def _dns_record(name_ref: bytes, rtype: int, ttl: int, data: str) -> bytes:
    rdata = _dns_rdata(rtype, data)
    return name_ref + struct.pack("!HHIH", rtype, 1, max(0, ttl), len(rdata)) + rdata


def _dns_soa(zone: str) -> bytes:
    rdata = (
        encode_dns_name(f"ns1.{zone}")
        + encode_dns_name(f"hostmaster.{zone}")
        + struct.pack("!IIIII", 2025102701, 7200, 1800, 1209600, 300)
    )
    return encode_dns_name(zone) + struct.pack("!HHIH", 6, 1, 3600, len(rdata)) + rdata


def _dns_flags(payload: Mapping[str, Any], *, response: bool) -> int:
    flags = payload.get("flags", {})
    value = 0x0100 if flags.get("rd", True) else 0
    if response:
        value |= 0x8000
        if flags.get("aa"):
            value |= 0x0400
        if flags.get("tc"):
            value |= 0x0200
        if flags.get("ra", True):
            value |= 0x0080
        value |= int(payload.get("rcode", {}).get("code", 0)) & 0x0F
    return value


def dns_query(payload: Mapping[str, Any]) -> bytes:
    query = payload.get("query", {})
    question = encode_dns_name(str(query.get("name", ""))) + struct.pack(
        "!HH", _DNS_TYPE_CODES.get(str(query.get("type", "A")), 1), 1
    )
    header = struct.pack(
        "!HHHHHH",
        int(payload.get("transaction_id", 0)) & 0xFFFF,
        _dns_flags(payload, response=False),
        1,
        0,
        0,
        0,
    )
    return header + question


def dns_response(payload: Mapping[str, Any]) -> bytes:
    query = payload.get("query", {})
    name = str(query.get("name", ""))
    qtype = _DNS_TYPE_CODES.get(str(query.get("type", "A")), 1)
    question = encode_dns_name(name) + struct.pack("!HH", qtype, 1)
    pointer = b"\xc0\x0c"
    answers = b"".join(
        _dns_record(
            pointer,
            _DNS_TYPE_CODES.get(str(answer.get("type", "A")), qtype),
            int(answer.get("ttl", 60)),
            str(answer.get("data", "")),
        )
        for answer in payload.get("answers", [])
    )
    authority = b""
    authority_count = 0
    if not payload.get("answers"):
        zone = name.split(".", 1)[1] if "." in name else name
        authority = _dns_soa(zone or "invalid")
        authority_count = 1
    header = struct.pack(
        "!HHHHHH",
        int(payload.get("transaction_id", 0)) & 0xFFFF,
        _dns_flags(payload, response=True),
        1,
        len(payload.get("answers", [])),
        authority_count,
        0,
    )
    return header + question + answers + authority


def _tls_record(content_type: int, version: int, fragment: bytes) -> bytes:
    return struct.pack("!BHH", content_type, version, len(fragment)) + fragment


def _handshake(msg_type: int, body: bytes) -> bytes:
    return struct.pack("!B", msg_type) + len(body).to_bytes(3, "big") + body


def _vector(body: bytes, size_bytes: int) -> bytes:
    return len(body).to_bytes(size_bytes, "big") + body


def _key_share_length(group: int) -> int:
    return {23: 65, 24: 97, 25: 133, 29: 32, 30: 56, 256: 256, 257: 384, 258: 512}.get(group, 32)


def _key_share_entry(group: int, label: str) -> bytes:
    size = _key_share_length(group)
    material = filler_bytes(f"{label}|ks|{group}", size)
    if group in {23, 24, 25}:
        material = b"\x04" + material[1:]
    return struct.pack("!H", group) + _vector(material, 2)


def _client_extension(ext: int, wire: TlsWire) -> bytes:
    profile = wire.client
    bodies: dict[int, bytes] = {
        0: _vector(b"\x00" + _vector(wire.sni.encode("ascii", "replace"), 2), 2),
        5: b"\x01\x00\x00\x00\x00",
        10: _vector(b"".join(struct.pack("!H", c) for c in profile.curves), 2),
        11: _vector(bytes(profile.point_formats), 1),
        13: _vector(b"".join(struct.pack("!H", s) for s in profile.signature_algorithms), 2),
        16: _vector(b"".join(_vector(a.encode(), 1) for a in profile.alpn), 2),
        18: b"",
        21: b"\x00" * 16,
        22: b"",
        23: b"",
        27: _vector(struct.pack("!H", 2), 1),
        28: struct.pack("!H", 16385),
        35: b"",
        43: _vector(b"".join(struct.pack("!H", v) for v in profile.supported_versions), 1),
        45: _vector(b"\x01", 1),
        51: _vector(_key_share_entry(profile.curves[0] if profile.curves else 29, wire.label), 2),
        65281: _vector(b"", 1),
    }
    return struct.pack("!HH", ext, len(bodies.get(ext, b""))) + bodies.get(ext, b"")


def client_hello(wire: TlsWire) -> bytes:
    profile = wire.client
    body = (
        struct.pack("!H", profile.legacy_version)
        + filler_bytes(f"{wire.label}|client-random", 32)
        + _vector(filler_bytes(f"{wire.label}|client-session", 32), 1)
        + _vector(b"".join(struct.pack("!H", c) for c in profile.ciphers), 2)
        + _vector(b"\x00", 1)
        + _vector(b"".join(_client_extension(e, wire) for e in profile.extensions), 2)
    )
    return _handshake(1, body)


def _server_extension(ext: int, wire: TlsWire) -> bytes:
    server = wire.server
    bodies: dict[int, bytes] = {
        0: b"",
        11: _vector(b"\x00", 1),
        16: _vector(_vector((server.alpn or "http/1.1").encode(), 1), 2),
        23: b"",
        35: b"",
        43: struct.pack("!H", server.selected_version),
        51: _key_share_entry(
            wire.client.curves[0] if wire.client.curves else 29, f"{wire.label}|server"
        ),
        65281: _vector(b"", 1),
    }
    return struct.pack("!HH", ext, len(bodies.get(ext, b""))) + bodies.get(ext, b"")


def server_hello(wire: TlsWire) -> bytes:
    server = wire.server
    body = (
        struct.pack("!H", server.legacy_version)
        + filler_bytes(f"{wire.label}|server-random", 32)
        + _vector(filler_bytes(f"{wire.label}|client-session", 32), 1)
        + struct.pack("!H", server.cipher)
        + b"\x00"
        + _vector(b"".join(_server_extension(e, wire) for e in server.extensions), 2)
    )
    return _handshake(2, body)


def certificate_message(chain: Sequence[bytes]) -> bytes:
    entries = b"".join(_vector(cert, 3) for cert in chain)
    return _handshake(11, _vector(entries, 3))


def _tls_flight(wire: TlsWire) -> tuple[bytes, bytes]:
    client = _tls_record(22, 0x0301, client_hello(wire))
    record_version = TLS12 if wire.server.selected_version >= TLS12 else wire.server.legacy_version
    server = _tls_record(22, record_version, server_hello(wire))
    if wire.server.selected_version == TLS13:
        server += _tls_record(20, TLS12, b"\x01")
        server += _tls_record(23, TLS12, filler_bytes(f"{wire.label}|enc-ext", 512))
        return client, server
    if wire.certificates:
        server += _tls_record(22, record_version, certificate_message(wire.certificates))
    server += _tls_record(
        22, record_version, _handshake(12, filler_bytes(f"{wire.label}|ske", 300))
    )
    server += _tls_record(22, record_version, _handshake(14, b""))
    return client, server


def _header_lines(headers: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        f"{header.get('name', 'X-Header')}: {header.get('value', '')}\r\n".encode()
        for header in headers
    )


def http_request(payload: Mapping[str, Any]) -> bytes:
    version = str(payload.get("version", "HTTP/1.1"))
    line = f"{payload.get('method', 'GET')} {payload.get('path', '/')} {version}\r\n".encode()
    body = str(payload.get("request_body", {}).get("preview", "")).encode()
    return line + _header_lines(payload.get("request_headers", [])) + b"\r\n" + body


def http_response(payload: Mapping[str, Any]) -> bytes:
    status = int(payload.get("status", 200))
    reason = _HTTP_REASONS.get(status, "Unknown")
    version = str(payload.get("version", "HTTP/1.1"))
    line = f"{version} {status} {reason}\r\n".encode()
    body = str(payload.get("response_body", {}).get("preview", "")).encode()
    return line + _header_lines(payload.get("response_headers", [])) + b"\r\n" + body


def ntp_packet(payload: Mapping[str, Any], *, client: bool, base_ms: int) -> bytes:
    version = int(payload.get("version", 4)) & 0x07
    mode = 3 if client else 4
    stratum = 0 if client else int(payload.get("stratum", 2))
    poll = int(payload.get("poll", 10)) & 0xFF
    ref_id = str(payload.get("ref_id", "GPS")).encode("ascii", "replace")[:4].ljust(4, b"\x00")
    seconds = base_ms // 1000 + 2208988800
    fraction = (base_ms % 1000) * 4294967
    stamp = struct.pack("!II", seconds & 0xFFFFFFFF, fraction & 0xFFFFFFFF)
    header = struct.pack(
        "!BBBbII4s",
        (0 << 6) | (version << 3) | mode,
        stratum,
        poll,
        -23,
        0x00000100,
        0x00000200,
        ref_id,
    )
    return header + stamp * 4


def ssh_kexinit(profile: SshProfile, label: str) -> bytes:
    lists = (
        ",".join(profile.kex),
        ",".join(profile.host_key_types),
        ",".join(profile.encryption),
        ",".join(profile.encryption),
        ",".join(profile.mac),
        ",".join(profile.mac),
        ",".join(profile.compression),
        ",".join(profile.compression),
        "",
        "",
    )
    body = bytearray(b"\x14" + filler_bytes(f"{label}|cookie", 16))
    for item in lists:
        raw = item.encode()
        body += struct.pack("!I", len(raw)) + raw
    body += b"\x00" + struct.pack("!I", 0)
    padding = 8 - ((len(body) + 5) % 8)
    if padding < 4:
        padding += 8
    return struct.pack("!IB", len(body) + padding + 1, padding) + bytes(body) + b"\x00" * padding


_SMB2_COMMANDS: Mapping[str, int] = {
    "NEGOTIATE": 0,
    "SESSION_SETUP": 1,
    "LOGOFF": 2,
    "TREE_CONNECT": 3,
    "TREE_DISCONNECT": 4,
    "CREATE": 5,
    "CLOSE": 6,
    "FLUSH": 7,
    "READ": 8,
    "WRITE": 9,
    "QUERY_INFO": 16,
}

_SMB2_REQUEST_SIZES: Mapping[int, int] = {0: 36, 1: 25, 3: 9, 5: 57, 6: 24, 8: 49, 9: 49, 16: 41}
_SMB2_RESPONSE_SIZES: Mapping[int, int] = {0: 65, 1: 9, 3: 16, 5: 89, 6: 60, 8: 17, 9: 17, 16: 9}


def smb2_message(
    command: str,
    *,
    message_id: int,
    tree_id: int,
    session_id: int,
    status: int,
    response: bool,
    extra: bytes = b"",
) -> bytes:
    code = _SMB2_COMMANDS.get(command.upper(), 0)
    sizes = _SMB2_RESPONSE_SIZES if response else _SMB2_REQUEST_SIZES
    structure_size = sizes.get(code, 9)
    header = struct.pack(
        "<4sHHIHHIIQIIQ16s",
        b"\xfeSMB",
        64,
        1,
        status if response else 0,
        code,
        1,
        1 if response else 0,
        0,
        message_id,
        0,
        tree_id,
        session_id,
        filler_bytes(f"smb|{session_id}|{message_id}", 16),
    )
    body = struct.pack("<H", structure_size) + b"\x00" * max(0, structure_size - 2) + extra
    return b"\x00" + (len(header) + len(body)).to_bytes(3, "big") + header + body


def _protocol_payload(row: Row, decoded: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = decoded.get(row.protocol, {})
    return inner if isinstance(inner, Mapping) else {}


def _udp_exchange(flow: Conversation, row: Row, payload: Mapping[str, Any]) -> None:
    if row.protocol == "dns":
        flow.datagram(UP, dns_query(payload))
        flow.datagram(DOWN, dns_response(payload))
        return
    if row.protocol == "ntp":
        flow.datagram(UP, ntp_packet(payload, client=True, base_ms=row.start_ms))
        flow.datagram(DOWN, ntp_packet(payload, client=False, base_ms=row.end_ms))
        return
    flow.datagram(UP, filler_bytes(f"udp|{row.id}|up", min(512, max(1, row.bytes_up))))
    flow.datagram(DOWN, filler_bytes(f"udp|{row.id}|down", min(512, max(1, row.bytes_down))))


def _smtp_exchange(flow: Conversation, payload: Mapping[str, Any]) -> None:
    helo = str(payload.get("helo", "mail.example.org"))
    mail_from = str(payload.get("mail_from", "sender@example.org"))
    recipients = [str(r) for r in payload.get("rcpt_to", []) if isinstance(r, str)]
    flow.send(DOWN, b"220 mx1.quillmere.example ESMTP ready\r\n")
    flow.send(UP, f"EHLO {helo}\r\n".encode())
    flow.send(DOWN, b"250-mx1.quillmere.example\r\n250-SIZE 52428800\r\n250 STARTTLS\r\n")
    flow.send(UP, f"MAIL FROM:<{mail_from}>\r\n".encode())
    flow.send(DOWN, b"250 2.1.0 Ok\r\n")
    for recipient in recipients or ["postmaster@quillmere.example"]:
        flow.send(UP, f"RCPT TO:<{recipient}>\r\n".encode())
        flow.send(DOWN, b"250 2.1.5 Ok\r\n")
    flow.send(UP, b"DATA\r\n")
    flow.send(DOWN, b"354 End data with <CR><LF>.<CR><LF>\r\n")
    headers = _header_lines(payload.get("headers", []))
    flow.send(UP, headers + b"\r\nMessage body omitted by the capture.\r\n.\r\n")
    flow.send(DOWN, b"250 2.0.0 Ok: queued\r\n")


def _smb2_exchange(flow: Conversation, row: Row, payload: Mapping[str, Any]) -> None:
    session = row.id & 0xFFFFFFFF
    tree = (row.id >> 8) & 0xFFFF
    message_id = 1
    for operation in payload.get("operations", []):
        if flow.writer.full:
            return
        command = str(operation.get("cmd", "READ"))
        status_name = str(operation.get("status", "STATUS_SUCCESS"))
        status = 0xC0000022 if status_name == "STATUS_ACCESS_DENIED" else 0
        path = str(operation.get("path", "")).encode("utf-16-le")
        flow.send(
            UP,
            smb2_message(
                command,
                message_id=message_id,
                tree_id=tree,
                session_id=session,
                status=0,
                response=False,
                extra=path,
            ),
        )
        flow.send(
            DOWN,
            smb2_message(
                command,
                message_id=message_id,
                tree_id=tree,
                session_id=session,
                status=status,
                response=True,
            ),
        )
        message_id += 1


def _ssh_exchange(flow: Conversation, row: Row, payload: Mapping[str, Any], ssh: SshWire) -> None:
    flow.send(UP, f"{payload.get('client_version', ssh.client.version)}\r\n".encode())
    flow.send(DOWN, f"{payload.get('server_version', ssh.server.version)}\r\n".encode())
    flow.send(UP, ssh_kexinit(ssh.client, f"ssh|{row.id}|client"))
    flow.send(DOWN, ssh_kexinit(ssh.server, f"ssh|{row.id}|server"))


def _tcp_exchange(
    flow: Conversation,
    row: Row,
    payload: Mapping[str, Any],
    tls: TlsWire | None,
    ssh: SshWire | None,
) -> None:
    if row.protocol == "http":
        flow.send(UP, http_request(payload))
        flow.send(DOWN, http_response(payload))
    elif row.protocol == "tls" and tls is not None:
        client_flight, server_flight = _tls_flight(tls)
        flow.send(UP, client_flight)
        flow.send(DOWN, server_flight)
        flow.send(UP, _tls_record(23, TLS12, filler_bytes(f"tls|{row.id}|c1", 256)))
    elif row.protocol == "smtp":
        _smtp_exchange(flow, payload)
    elif row.protocol == "smb2":
        _smb2_exchange(flow, row, payload)
    elif row.protocol == "ssh" and ssh is not None:
        _ssh_exchange(flow, row, payload, ssh)
    else:
        first = str(payload.get("first_payload_hex", ""))
        try:
            opening = bytes.fromhex(first)
        except ValueError:
            opening = b""
        flow.send(UP, opening or filler_bytes(f"tcp|{row.id}", 64))


def _fill(flow: Conversation, row: Row) -> None:
    up = max(0, row.bytes_up - flow.sent[UP])
    down = max(0, row.bytes_down - flow.sent[DOWN])
    index = 0
    while not flow.writer.full and (up > 0 or down > 0):
        if up >= down and up > 0:
            size = min(MSS, up)
            up -= size
            direction = UP
        elif down > 0:
            size = min(MSS, down)
            down -= size
            direction = DOWN
        else:
            return
        if not flow.segment(direction, PSH | ACK, filler_bytes(f"pad|{row.id}|{index}", size)):
            return
        index += 1
        if not flow.writer.full:
            flow.segment(DOWN if direction == UP else UP, ACK)


def _step_us(row: Row) -> int:
    span = max(1, row.end_ms - row.start_ms) * 1000
    return max(1, min(span // MAX_PACKETS, 2_000_000))


def build_pcap(
    row: Row,
    decoded: Mapping[str, Any],
    *,
    tls: TlsWire | None = None,
    ssh: SshWire | None = None,
) -> bytes:
    payload = _protocol_payload(row, decoded)
    writer = PacketWriter(row.start_ms * 1000, _step_us(row))
    isn = int.from_bytes(hashlib.blake2b(str(row.id).encode(), digest_size=8).digest(), "big")
    flow = Conversation(
        writer,
        src_ip=row.src_ip,
        src_port=row.src_port,
        dst_ip=row.dst_ip,
        dst_port=row.dst_port,
        isn_up=isn >> 32,
        isn_down=isn & 0xFFFFFFFF,
    )
    if row.transport == "udp":
        _udp_exchange(flow, row, payload)
        return writer.to_bytes()
    if not flow.handshake():
        return writer.to_bytes()
    _tcp_exchange(flow, row, payload, tls, ssh)
    _fill(flow, row)
    flow.finish()
    return writer.to_bytes()
