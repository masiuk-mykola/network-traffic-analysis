import ipaddress
from collections.abc import Mapping, Sequence
from typing import Literal

from capture_api.world.catalog import COUNTRIES
from capture_api.world.rng import stable_int
from capture_api.world.types import EnrichData, HostInfo

COUNTRY_CODES: tuple[str, ...] = tuple(COUNTRIES)

DOCUMENTATION_ASNS: tuple[int, ...] = tuple(range(64496, 64512))
"""RFC 5398 documentation ASNs — the only ASNs this simulator ever reports."""

ASN_ORGS: Mapping[int, str] = {
    64496: "Example Hosting Ltd",
    64497: "Northmoor Telecom",
    64498: "Bluequay Networks",
    64499: "Marrowfield Communications",
    64500: "Thornrise Cloud Services",
    64501: "Saltgate Internet",
    64502: "Pellmere Datacentres",
    64503: "Greyharbour Transit",
    64504: "Aldervane Broadband",
    64505: "Quietbrook Systems",
    64506: "Fenmarket Networks",
    64507: "Cobblewend Hosting",
    64508: "Ironvale Carrier",
    64509: "Tidewrack Edge",
    64510: "Hollowport Telecom",
    64511: "Reedbank Infrastructure",
}

CLEAN_SHARE = 920
SUSPICIOUS_SHARE = 990
"""Out of 1000: mostly clean, ~7 % suspicious, ~1 % malicious."""


INTERNAL_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("2001:db8:20::/48"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
)
"""The monitored network's own space. The RFC 5737 / ``2001:db8::`` ranges this simulator uses
as *external* peers answer ``True`` to Python's ``is_private``, so membership is tested against
this list instead — which also means the internal IPv6 plan (``2001:db8:20::/48``: the resolver
and the dual-stacked HQ workstations) has to be named here, or internal hosts would enrich as
foreign peers. External IPv6 peers live in ``2001:db8:ff::/48``."""


def _address(ip: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(ip)
    except ValueError:
        return None


def _is_internal_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        address in network for network in INTERNAL_NETWORKS if network.version == address.version
    )


def is_internal(ip: str) -> bool:
    address = _address(ip)
    return address is not None and _is_internal_address(address)


def _network_key(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if isinstance(address, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{address}/26", strict=False).network_address)
    return str(ipaddress.ip_network(f"{address}/48", strict=False).network_address)


def country_for_ip(seed: str, ip: str) -> str | None:
    address = _address(ip)
    if address is None or _is_internal_address(address):
        return None
    index = stable_int(seed, "country", _network_key(address)) % len(COUNTRY_CODES)
    return COUNTRY_CODES[index]


def asn_for_ip(seed: str, ip: str) -> int | None:
    address = _address(ip)
    if address is None or _is_internal_address(address):
        return None
    index = stable_int(seed, "asn", _network_key(address)) % len(DOCUMENTATION_ASNS)
    return DOCUMENTATION_ASNS[index]


type Verdict = Literal["clean", "suspicious", "malicious"]


def _reputation(seed: str, ip: str, *, suspicious: bool) -> Verdict:
    if suspicious:
        return "suspicious"
    draw = stable_int(seed, "reputation", ip, bits=20) % 1000
    if draw < CLEAN_SHARE:
        return "clean"
    if draw < SUSPICIOUS_SHARE:
        return "suspicious"
    return "malicious"


def enrich_ip(
    seed: str,
    ip: str,
    *,
    host: HostInfo | None = None,
    flagged: Sequence[str] = (),
) -> EnrichData:
    address = _address(ip)
    if address is None or _is_internal_address(address):
        return EnrichData(ip=ip, reputation="unknown")
    asn = asn_for_ip(seed, ip)
    country = (host.country if host is not None and host.country else None) or country_for_ip(
        seed, ip
    )
    return EnrichData(
        ip=ip,
        reputation=_reputation(seed, ip, suspicious=ip in set(flagged)),
        country=country,
        asn=f"AS{asn}" if asn is not None else None,
        org=ASN_ORGS.get(asn, "Example Hosting Ltd") if asn is not None else None,
    )
