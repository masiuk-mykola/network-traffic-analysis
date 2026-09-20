import ipaddress

import pytest

from capture_api.world.enrich_data import INTERNAL_NETWORKS, is_internal
from capture_api.world.network import Network, country_for_ip
from capture_api.world.types import Row
from capture_api.world.world import SimWorld
from tests.integration.conftest import all_rows

INTERNAL_SAMPLES = (
    "10.20.0.53",
    "10.20.1.10",
    "10.20.4.10",
    "10.20.40.23",
    "2001:db8:20::53",
    "2001:db8:20:4::a",
)
EXTERNAL_SAMPLES = ("192.0.2.10", "198.51.100.20", "203.0.113.130", "2001:db8:ff:1::10")


@pytest.mark.parametrize("ip", INTERNAL_SAMPLES)
def test_internal_space_has_no_country_asn_or_reputation(demo: SimWorld, ip: str) -> None:
    assert is_internal(ip)
    assert country_for_ip(demo.seed, ip) is None
    enriched = demo.enrich(ip)
    assert enriched.country is None
    assert enriched.asn is None
    assert enriched.org is None
    assert enriched.reputation == "unknown"


@pytest.mark.parametrize("ip", EXTERNAL_SAMPLES)
def test_external_space_is_enriched(demo: SimWorld, ip: str) -> None:
    assert not is_internal(ip)
    assert demo.enrich(ip).country == country_for_ip(demo.seed, ip)
    assert demo.enrich(ip).asn is not None


def test_the_internal_ipv6_plan_is_declared_internal() -> None:
    plan = ipaddress.ip_network("2001:db8:20::/48")
    assert any(
        network.version == 6 and plan.subnet_of(network)  # type: ignore[arg-type]
        for network in INTERNAL_NETWORKS
        if network.version == 6
    )


def _one_row_per_address(world: SimWorld) -> dict[str, Row]:
    found: dict[str, Row] = {}
    for row in all_rows(world):
        found.setdefault(row.src_ip, row)
        found.setdefault(row.dst_ip, row)
    return found


def _grid_country(world: SimWorld, ip: str, row: Row) -> str | None:
    view = world.to_session_row(row)
    return view.src.country if view.src.ip == ip else view.dst.country


def test_every_address_in_the_history_enriches_the_way_the_grid_shows_it(
    demo: SimWorld,
) -> None:
    rows = _one_row_per_address(demo)
    assert len(rows) > 100
    for ip, row in rows.items():
        assert _grid_country(demo, ip, row) == demo.enrich(ip).country, ip


def test_the_c2_and_sender_addresses_carry_a_country_in_the_grid(demo: SimWorld) -> None:
    incident = demo.incident()
    rows = _one_row_per_address(demo)
    for ip in (incident.c2_ip, incident.lookalike_sender_ip):
        assert demo.host(ip) is None, "scripted peers are deliberately not in the host table"
        country = _grid_country(demo, ip, rows[ip])
        assert country is not None
        assert country == demo.enrich(ip).country


def test_hosts_built_by_the_network_use_the_same_rule() -> None:
    network = Network("demo")
    for host in network.hosts():
        assert host.country == country_for_ip("demo", host.ip)
