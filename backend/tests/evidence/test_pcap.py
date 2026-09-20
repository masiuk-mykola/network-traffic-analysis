import struct
from typing import Any

import pytest

from capture_api.world.decode import build_evidence_engine
from capture_api.world.pcap import (
    ETHERTYPE_IPV4,
    ETHERTYPE_IPV6,
    MAX_PACKETS,
    PROTO_TCP,
    PROTO_UDP,
    SNAPLEN,
    dns_query,
    dns_response,
    encode_dns_name,
)

from .factories import FakeContext, make_row

PROTOCOLS = ("dns", "http", "tls", "smtp", "smb2", "ssh", "ntp", "tcp")


def packets(data: bytes) -> list[tuple[int, int, bytes]]:
    magic, major, minor, _, _, snaplen, link = struct.unpack("<IHHiIII", data[:24])
    assert magic == 0xA1B2C3D4
    assert (major, minor) == (2, 4)
    assert snaplen == SNAPLEN
    assert link == 1
    out = []
    offset = 24
    while offset < len(data):
        ts_sec, ts_usec, incl, orig = struct.unpack("<IIII", data[offset : offset + 16])
        assert incl == orig
        frame = data[offset + 16 : offset + 16 + incl]
        assert len(frame) == incl
        out.append((ts_sec, ts_usec, frame))
        offset += 16 + incl
    return out


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum((data[i] << 8) | data[i + 1] for i in range(0, len(data), 2))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


@pytest.fixture
def engine() -> Any:
    return build_evidence_engine(FakeContext())


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_file_parses_and_respects_the_cap(engine: Any, protocol: str) -> None:
    data = engine.pcap(make_row(protocol))
    frames = packets(data)
    assert 0 < len(frames) <= MAX_PACKETS


def test_large_transfers_stop_at_the_cap(engine: Any) -> None:
    row = make_row("http", bytes_up=900_000_000, bytes_down=4_000, duration_ms=120_000)
    assert len(packets(engine.pcap(row))) == MAX_PACKETS


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_bytes_are_deterministic(protocol: str) -> None:
    row = make_row(protocol)
    first = build_evidence_engine(FakeContext()).pcap(row)
    second = build_evidence_engine(FakeContext()).pcap(row)
    assert first == second


def test_timestamps_start_at_the_session_start_and_ascend(engine: Any) -> None:
    row = make_row("tls")
    frames = packets(engine.pcap(row))
    assert frames[0][0] == row.start_ms // 1000
    stamps = [(sec, usec) for sec, usec, _ in frames]
    assert stamps == sorted(stamps)


def test_ipv4_header_checksums_are_correct(engine: Any) -> None:
    for _, _, frame in packets(engine.pcap(make_row("tls"))):
        assert struct.unpack("!H", frame[12:14])[0] == ETHERTYPE_IPV4
        header = frame[14:34]
        assert checksum(header) == 0
        assert header[9] in {PROTO_TCP, PROTO_UDP}


def test_macs_are_locally_administered(engine: Any) -> None:
    for _, _, frame in packets(engine.pcap(make_row("dns"))):
        assert frame[0:2] == b"\x02\x00"
        assert frame[6:8] == b"\x02\x00"


def test_ipv6_sessions_are_framed_as_ipv6(engine: Any) -> None:
    row = make_row("dns", src_ip="2001:db8:20:4::17", dst_ip="2001:db8:ff::53")
    for _, _, frame in packets(engine.pcap(row)):
        assert struct.unpack("!H", frame[12:14])[0] == ETHERTYPE_IPV6
        assert frame[14] >> 4 == 6


def test_tcp_handshake_and_sequence_numbers(engine: Any) -> None:
    frames = [frame for _, _, frame in packets(engine.pcap(make_row("tls")))]
    first, second, third = (frame[34:] for frame in frames[:3])
    syn_seq = struct.unpack("!I", first[4:8])[0]
    assert first[13] == 0x02
    assert second[13] == 0x12
    assert struct.unpack("!I", second[8:12])[0] == syn_seq + 1
    assert third[13] == 0x10
    assert struct.unpack("!I", third[4:8])[0] == syn_seq + 1


def test_udp_sessions_are_two_datagrams(engine: Any) -> None:
    frames = packets(engine.pcap(make_row("dns")))
    assert len(frames) == 2
    assert frames[0][2][23] == PROTO_UDP


def test_dns_wire_matches_the_decoded_view(engine: Any) -> None:
    row = make_row("dns")
    decoded = engine.canonical(row).payload["dns"]
    query = dns_query(decoded)
    assert query[:2] == struct.pack("!H", decoded["transaction_id"])
    assert encode_dns_name("telemetry.cdn-metrics.test") in query
    response = dns_response(decoded)
    assert struct.unpack("!H", response[6:8])[0] == 1
    assert bytes((203, 0, 113, 24)) in response


def test_nxdomain_response_has_the_rcode_and_an_authority_record(engine: Any) -> None:
    row = make_row("dns", attrs={"dns.rcode": "NXDOMAIN", "dns.answer": ()})
    decoded = engine.canonical(row).payload["dns"]
    response = dns_response(decoded)
    assert struct.unpack("!H", response[2:4])[0] & 0x0F == 3
    assert struct.unpack("!H", response[6:8])[0] == 0
    assert struct.unpack("!H", response[8:10])[0] == 1


def test_http_request_bytes_are_in_the_capture(engine: Any) -> None:
    row = make_row("http")
    body = b"".join(frame for _, _, frame in packets(engine.pcap(row)))
    assert b"PUT /bkt/obj-0004821 HTTP/1.1\r\n" in body
    assert b"HTTP/1.1 200 OK\r\n" in body


def test_certificates_from_the_decoded_chain_are_in_the_capture(engine: Any) -> None:
    row = make_row("tls")
    decoded = engine.canonical(row)
    body = b"".join(frame for _, _, frame in packets(engine.pcap(row)))
    for certificate in decoded.tls.certificates:
        assert certificate in body
