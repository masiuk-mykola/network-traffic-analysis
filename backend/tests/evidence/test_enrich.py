import pytest

from capture_api.world.catalog import COUNTRIES
from capture_api.world.decode import build_evidence_engine
from capture_api.world.enrich_data import (
    ASN_ORGS,
    DOCUMENTATION_ASNS,
    asn_for_ip,
    country_for_ip,
    enrich_ip,
    is_internal,
)

from .factories import INCIDENT, SEED, FakeContext

EXTERNAL = ("192.0.2.10", "198.51.100.31", "203.0.113.24", "2001:db8:ff::10")


@pytest.mark.parametrize("ip", ["10.20.4.17", "10.20.1.10", "10.20.40.9"])
def test_internal_addresses_are_unknown(ip: str) -> None:
    result = enrich_ip(SEED, ip)
    assert is_internal(ip)
    assert result.reputation == "unknown"
    assert result.asn is None
    assert result.org is None
    assert result.country is None


def test_a_malformed_address_is_unknown() -> None:
    assert enrich_ip(SEED, "not-an-address").reputation == "unknown"


@pytest.mark.parametrize("ip", EXTERNAL)
def test_external_addresses_get_a_documentation_asn(ip: str) -> None:
    result = enrich_ip(SEED, ip)
    assert result.asn is not None
    assert int(result.asn.removeprefix("AS")) in DOCUMENTATION_ASNS
    assert result.org in set(ASN_ORGS.values())
    assert result.country in COUNTRIES
    assert result.reputation in {"clean", "suspicious", "malicious"}


def test_asn_and_country_are_stable_per_subnet() -> None:
    assert asn_for_ip(SEED, "203.0.113.1") == asn_for_ip(SEED, "203.0.113.60")
    assert country_for_ip(SEED, "203.0.113.1") == country_for_ip(SEED, "203.0.113.60")
    assert asn_for_ip(SEED, "10.20.4.1") is None


def test_known_hosts_keep_their_country() -> None:
    ctx = FakeContext()
    host = ctx.host("192.0.2.10")
    assert host is not None
    assert enrich_ip(SEED, "192.0.2.10", host=host).country == host.country


def test_flagged_infrastructure_is_suspicious_not_malicious() -> None:
    engine = build_evidence_engine(FakeContext())
    for ip in (INCIDENT.c2_ip, INCIDENT.c2_upload_ip, INCIDENT.lookalike_sender_ip):
        assert engine.enrich(ip).reputation == "suspicious"


def test_reputations_are_mostly_clean() -> None:
    verdicts = [enrich_ip(SEED, f"203.0.113.{host}").reputation for host in range(1, 255)]
    assert verdicts.count("clean") > 200
    assert verdicts.count("malicious") < 20


def test_enrichment_is_deterministic() -> None:
    first = build_evidence_engine(FakeContext()).enrich("198.51.100.77")
    second = build_evidence_engine(FakeContext()).enrich("198.51.100.77")
    assert first == second
