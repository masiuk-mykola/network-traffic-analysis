import pytest

from capture_api.world.world import SimWorld
from tests.integration.conftest import all_rows, world_for

PCAP_HEADER_BYTES = 24
LIBPCAP_MAGICS = (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1")


def _is_v6(address: str) -> bool:
    return ":" in address


@pytest.mark.parametrize("seed", ["demo", "alpha"])
def test_no_row_mixes_address_families(seed: str) -> None:
    world = world_for(seed)
    mixed = [row for row in all_rows(world) if _is_v6(row.src_ip) != _is_v6(row.dst_ip)]
    assert not mixed, [(row.id, row.src_ip, row.dst_ip) for row in mixed[:5]]


def test_some_sessions_really_are_ipv6(demo: SimWorld) -> None:
    v6 = [row for row in all_rows(demo) if _is_v6(row.src_ip)]
    assert v6, "the world declares IPv6 traffic but generated none"
    assert {row.sensor_id for row in v6} == {"hq-core"}
    assert {row.protocol for row in v6} <= {"dns", "tls", "http"}


def test_every_ipv6_session_renders_a_valid_pcap(demo: SimWorld) -> None:
    v6 = [row for row in all_rows(demo) if _is_v6(row.src_ip)]
    rendered = 0
    for row in v6:
        if not demo.pcap_status(row).available:
            continue
        blob = demo.pcap(row)
        assert blob[:4] in LIBPCAP_MAGICS, row.id
        assert len(blob) > PCAP_HEADER_BYTES, row.id
        rendered += 1
    assert rendered > 0
