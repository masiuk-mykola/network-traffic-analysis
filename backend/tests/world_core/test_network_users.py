import ipaddress
import re

import pytest

from capture_api.world.catalog import COUNTRIES, DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.network import (
    BACKUP_HOST,
    EXTERNAL_SERVICES,
    VENDOR_UPDATE_HOST,
    Network,
    country_for_ip,
    short_name,
)
from capture_api.world.users import FIRST_NAMES, LAST_NAMES, assign_users, display_name, mailbox

ALLOWED_V4 = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.20.0.0/16", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)
ALLOWED_V6 = (ipaddress.ip_network("2001:db8::/32"),)
ALLOWED_SUFFIXES = (".example", ".test", ".invalid", "example.com", "example.net", "example.org")


def test_every_address_is_documentation_space() -> None:
    network = Network("demo")
    for host in network.hosts():
        for raw in (host.ip, host.ipv6):
            if raw is None:
                continue
            address = ipaddress.ip_address(raw)
            pools = ALLOWED_V6 if address.version == 6 else ALLOWED_V4
            assert any(address in pool for pool in pools), raw


def test_every_name_is_fictional() -> None:
    network = Network("demo")
    for host in network.hosts():
        assert host.hostname is not None
        assert host.hostname.endswith(ALLOWED_SUFFIXES), host.hostname


def test_internal_plan_matches_the_spec() -> None:
    network = Network("demo")
    assert network.resolver.ip == "10.20.0.53"
    assert short_name(network.resolver.hostname) == "ns1"
    assert [short_name(s.hostname) for s in network.servers] == [
        "dc01",
        "fs01",
        "bkp01",
        "app01",
        "jump01",
    ]
    assert network.server("fs01").ip == "10.20.1.10"
    assert network.mail_gateway.ip == "10.20.2.25"
    assert network.scanner.ip == "10.20.9.250"
    assert len(network.hq_workstations) == 160
    assert len(network.branch_workstations) == 60
    assert len(network.printers) == 20
    assert all(h.sensor_id == DC_EAST for h in network.servers)
    assert all(h.sensor_id == HQ_CORE for h in network.hq_workstations)
    assert all(h.sensor_id == HARBOR_BRANCH for h in network.branch_workstations)
    assert network.workstations(DC_EAST) == ()


def test_hq_workstations_have_ipv6_and_resolve_both_ways() -> None:
    network = Network("demo")
    workstation = network.hq_workstations[0]
    assert workstation.ipv6 is not None
    assert network.host(workstation.ipv6) is workstation
    assert network.host(workstation.ip) is workstation
    assert network.host("10.99.99.99") is None
    assert all(h.ipv6 is None for h in network.branch_workstations)


def test_external_services_and_red_herrings() -> None:
    network = Network("demo")
    assert 40 <= len(EXTERNAL_SERVICES) <= 50
    assert len({s.domain for s in EXTERNAL_SERVICES}) == len(EXTERNAL_SERVICES)
    assert network.service(VENDOR_UPDATE_HOST) is not None
    assert network.service(BACKUP_HOST) is not None
    assert network.service("nope.example") is None
    ipv6 = network.ipv6_services()
    assert ipv6
    assert all(s.ipv6 is not None and s.ipv6.startswith("2001:db8:ff:") for s in ipv6)
    assert network.service_for_ip("192.0.2.10") is network.service("static.example.com")
    assert all(s.tls is False for s in network.services("ntp"))


def test_countries_are_per_slash_26_and_internal_addresses_have_none() -> None:
    network = Network("demo")
    assert country_for_ip("demo", "192.0.2.65") == country_for_ip("demo", "192.0.2.100")
    assert country_for_ip("demo", "192.0.2.70") != country_for_ip("demo", "192.0.2.10")
    assert country_for_ip("demo", "10.20.4.10") is None
    assert country_for_ip("demo", "2001:db8:20:4::a") is None
    assert all(host.country is None for host in network.hosts() if host.kind == "internal")
    external = {host.country for host in network.hosts() if host.kind == "external"}
    assert external <= set(COUNTRIES)
    assert len(external) >= 5


def test_country_assignment_is_seed_varied() -> None:
    demo = {h.ip: h.country for h in Network("demo").hosts() if h.kind == "external"}
    other = {h.ip: h.country for h in Network("other").hosts() if h.kind == "external"}
    assert demo != other


def test_free_ips_skips_benign_services() -> None:
    network = Network("demo")
    free = list(network.free_ips("203.0.113", 192, 249))
    assert len(free) == 58
    assert all(network.host(ip) is None for ip in free)


def test_user_pool_is_large_and_deterministic() -> None:
    assert len(FIRST_NAMES) + len(LAST_NAMES) >= 240
    assert len(set(FIRST_NAMES)) == len(FIRST_NAMES)
    assert len(set(LAST_NAMES)) == len(LAST_NAMES)
    users = assign_users("demo", 220)
    assert len(set(users)) == 220
    assert users == assign_users("demo", 220)
    assert users != assign_users("other", 220)
    assert all(re.fullmatch(r"[a-z]+\.[a-z]+", user) for user in users)
    assert mailbox(users[0]).endswith("@quillmere.example")
    assert display_name("marta.kowalczyk") == "Marta Kowalczyk"


def test_assign_users_rejects_an_impossible_request() -> None:
    with pytest.raises(ValueError, match="distinct users"):
        assign_users("demo", len(FIRST_NAMES) * len(LAST_NAMES) + 1)


def test_every_workstation_has_a_distinct_primary_user() -> None:
    network = Network("demo")
    users = [h.user for h in network.hq_workstations + network.branch_workstations]
    assert all(users)
    assert len(set(users)) == len(users)
