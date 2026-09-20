from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from capture_api.world.catalog import DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.enrich_data import country_for_ip as enrich_country
from capture_api.world.types import HostInfo
from capture_api.world.users import assign_users

DOMAIN = "quillmere.example"

RESOLVER_IP = "10.20.0.53"
RESOLVER_IPV6 = "2001:db8:20::53"
MAIL_GATEWAY_IP = "10.20.2.25"
SCANNER_IP = "10.20.9.250"

HQ_WORKSTATION_COUNT = 160
BRANCH_WORKSTATION_COUNT = 60
PRINTER_COUNT = 20
HOST_OFFSET = 10
"""First usable host number in each workstation/printer subnet."""

VENDOR_UPDATE_HOST = "updates.vendor.example"
BACKUP_HOST = "backup.vaultstore.example"

C2_IP_FIRST, C2_IP_LAST = 192, 249
"""Reserved tail of ``203.0.113.0/24``: no benign service lives there (incident use)."""

SENDER_IP_FIRST, SENDER_IP_LAST = 200, 249
"""Reserved tail of ``198.51.100.0/24``: look-alike sender and the ``http_put`` bucket."""


@dataclass(frozen=True, slots=True)
class ExternalService:
    domain: str
    ips: tuple[str, ...]
    kind: str
    """``cdn|docs|mail|saas|chat|video|maps|ntp|search|news|forum|messaging|ads|telemetry|
    updates|backup|payments|api|identity|storage|software|logistics``."""
    ipv6: str | None = None
    tls: bool = True
    """Whether TLS traffic to this service is plausible (NTP peers are UDP only)."""


EXTERNAL_SERVICES: tuple[ExternalService, ...] = (
    ExternalService("static.example.com", ("192.0.2.10", "192.0.2.11"), "cdn", "2001:db8:ff:1::10"),
    ExternalService("cdn.example.net", ("192.0.2.20",), "cdn", "2001:db8:ff:1::20"),
    ExternalService("assets.example.org", ("192.0.2.24",), "cdn"),
    ExternalService("fonts.example.com", ("192.0.2.28",), "cdn"),
    ExternalService("docs.example.org", ("192.0.2.35",), "docs", "2001:db8:ff:2::35"),
    ExternalService("wiki.example.org", ("192.0.2.38",), "docs"),
    ExternalService("mail.example.org", ("192.0.2.44",), "mail"),
    ExternalService("smtp-relay.example.net", ("192.0.2.48",), "mail"),
    ExternalService("crm.example.com", ("192.0.2.60",), "saas"),
    ExternalService("erp.example.com", ("192.0.2.64",), "saas"),
    ExternalService("hr.example.net", ("192.0.2.68",), "saas"),
    ExternalService("chat.example.com", ("192.0.2.80",), "chat", "2001:db8:ff:2::80"),
    ExternalService("meet.example.net", ("192.0.2.84",), "video"),
    ExternalService("video.example.net", ("192.0.2.88",), "video", "2001:db8:ff:4::88"),
    ExternalService("stream.example.org", ("192.0.2.92",), "video"),
    ExternalService("maps.example.net", ("192.0.2.100",), "maps"),
    ExternalService("weather.example.net", ("192.0.2.104",), "maps"),
    ExternalService("time.example.net", ("192.0.2.123",), "ntp", tls=False),
    ExternalService("ntp2.example.org", ("192.0.2.124",), "ntp", tls=False),
    ExternalService("search.example.com", ("192.0.2.130",), "search", "2001:db8:ff:3::130"),
    ExternalService("news.example.org", ("192.0.2.140",), "news", "2001:db8:ff:4::140"),
    ExternalService("blog.example.org", ("192.0.2.144",), "news"),
    ExternalService("forum.example.net", ("192.0.2.148",), "forum"),
    ExternalService("push.example.org", ("192.0.2.160",), "messaging"),
    ExternalService("ads.example.net", ("192.0.2.200",), "ads"),
    ExternalService("analytics.example.net", ("192.0.2.180",), "telemetry"),
    ExternalService("metrics.example.org", ("192.0.2.210",), "telemetry"),
    ExternalService(VENDOR_UPDATE_HOST, ("198.51.100.10",), "updates"),
    ExternalService(BACKUP_HOST, ("198.51.100.20", "198.51.100.21"), "backup"),
    ExternalService("pay.example.com", ("198.51.100.30",), "payments"),
    ExternalService("invoices.example.net", ("198.51.100.34",), "payments"),
    ExternalService("bank.example.org", ("198.51.100.38",), "payments"),
    ExternalService("api.example.com", ("198.51.100.50",), "api", "2001:db8:ff:3::50"),
    ExternalService("api.example.net", ("198.51.100.54",), "api"),
    ExternalService("auth.example.com", ("198.51.100.90",), "identity"),
    ExternalService("sso.example.org", ("198.51.100.100",), "identity"),
    ExternalService("files.example.net", ("198.51.100.130",), "storage"),
    ExternalService("share.example.com", ("198.51.100.140",), "storage"),
    ExternalService("repo.example.org", ("203.0.113.10",), "software"),
    ExternalService("packages.example.net", ("203.0.113.14",), "software"),
    ExternalService("registry.example.com", ("203.0.113.18",), "software"),
    ExternalService("ticketing.example.net", ("203.0.113.70",), "saas"),
    ExternalService("support.example.com", ("203.0.113.74",), "saas"),
    ExternalService("shipping.example.org", ("203.0.113.100",), "logistics"),
    ExternalService("customs.example.net", ("203.0.113.130",), "logistics"),
    ExternalService("portauthority.example.org", ("203.0.113.140",), "logistics"),
    ExternalService("telemetry.example.com", ("203.0.113.150",), "telemetry"),
)
"""~45 benign external services. Two of them are the seeded red herrings."""

SERVER_HOSTS: tuple[tuple[str, str, str], ...] = (
    ("dc01", "10.20.1.5", "server"),
    ("fs01", "10.20.1.10", "server"),
    ("bkp01", "10.20.1.20", "server"),
    ("app01", "10.20.1.30", "server"),
    ("jump01", "10.20.1.40", "server"),
)


def country_for_ip(seed: str, ip: str) -> str | None:
    return enrich_country(seed, ip)


def fqdn(short: str) -> str:
    return f"{short}.{DOMAIN}"


def short_name(hostname: str | None) -> str | None:
    if hostname is None:
        return None
    return hostname.removesuffix(f".{DOMAIN}")


class Network:
    __slots__ = (
        "_branch_workstations",
        "_by_domain",
        "_by_ip",
        "_by_ipv6",
        "_hosts",
        "_hq_workstations",
        "_printers",
        "_seed",
        "_servers",
        "_service_by_ip",
    )

    def __init__(self, seed: str) -> None:
        self._seed = seed
        users = assign_users(seed, HQ_WORKSTATION_COUNT + BRANCH_WORKSTATION_COUNT)
        self._hq_workstations = tuple(
            _workstation("ws-hq", i, f"10.20.4.{HOST_OFFSET + i - 1}", HQ_CORE, users[i - 1])
            for i in range(1, HQ_WORKSTATION_COUNT + 1)
        )
        self._branch_workstations = tuple(
            _workstation(
                "ws-hb",
                i,
                f"10.20.40.{HOST_OFFSET + i - 1}",
                HARBOR_BRANCH,
                users[HQ_WORKSTATION_COUNT + i - 1],
                with_ipv6=False,
            )
            for i in range(1, BRANCH_WORKSTATION_COUNT + 1)
        )
        self._printers = tuple(
            HostInfo(
                ip=f"10.20.8.{HOST_OFFSET + i - 1}",
                hostname=fqdn(f"prn-{i:02d}"),
                kind="internal",
                role="printer",
                sensor_id=HQ_CORE,
            )
            for i in range(1, PRINTER_COUNT + 1)
        )
        self._servers = tuple(
            HostInfo(ip=ip, hostname=fqdn(name), kind="internal", role=role, sensor_id=DC_EAST)
            for name, ip, role in SERVER_HOSTS
        )
        internal = (
            HostInfo(
                ip=RESOLVER_IP,
                hostname=fqdn("ns1"),
                kind="internal",
                role="resolver",
                sensor_id=HQ_CORE,
                ipv6=RESOLVER_IPV6,
            ),
            HostInfo(
                ip=MAIL_GATEWAY_IP,
                hostname=fqdn("mx1"),
                kind="internal",
                role="mail",
                sensor_id=HQ_CORE,
            ),
            HostInfo(
                ip=SCANNER_IP,
                hostname=fqdn("scan-it-01"),
                kind="internal",
                role="scanner",
                sensor_id=HQ_CORE,
            ),
            *self._servers,
            *self._hq_workstations,
            *self._printers,
            *self._branch_workstations,
        )
        external: list[HostInfo] = []
        service_by_ip: dict[str, ExternalService] = {}
        for service in EXTERNAL_SERVICES:
            for ip in (*service.ips, *((service.ipv6,) if service.ipv6 else ())):
                external.append(
                    HostInfo(
                        ip=ip,
                        hostname=service.domain,
                        kind="external",
                        role="service",
                        country=country_for_ip(seed, ip),
                    )
                )
                service_by_ip[ip] = service
        self._hosts: tuple[HostInfo, ...] = (*internal, *external)
        self._by_ip: Mapping[str, HostInfo] = {host.ip: host for host in self._hosts}
        self._by_ipv6: Mapping[str, HostInfo] = {
            host.ipv6: host for host in self._hosts if host.ipv6
        }
        self._by_domain: Mapping[str, ExternalService] = {s.domain: s for s in EXTERNAL_SERVICES}
        self._service_by_ip: Mapping[str, ExternalService] = service_by_ip
        if len(self._by_ip) != len(self._hosts):
            raise ValueError("duplicate address in the network plan")

    @property
    def seed(self) -> str:
        return self._seed

    def host(self, ip: str) -> HostInfo | None:
        return self._by_ip.get(ip) or self._by_ipv6.get(ip)

    def hosts(self) -> Sequence[HostInfo]:
        return self._hosts

    def hostname(self, ip: str) -> str | None:
        host = self.host(ip)
        return host.hostname if host else None

    def country(self, ip: str) -> str | None:
        host = self.host(ip)
        return host.country if host else None

    def service(self, domain: str) -> ExternalService | None:
        return self._by_domain.get(domain)

    def service_for_ip(self, ip: str) -> ExternalService | None:
        return self._service_by_ip.get(ip)

    @property
    def resolver(self) -> HostInfo:
        return self._by_ip[RESOLVER_IP]

    @property
    def mail_gateway(self) -> HostInfo:
        return self._by_ip[MAIL_GATEWAY_IP]

    @property
    def scanner(self) -> HostInfo:
        return self._by_ip[SCANNER_IP]

    @property
    def servers(self) -> tuple[HostInfo, ...]:
        return self._servers

    @property
    def printers(self) -> tuple[HostInfo, ...]:
        return self._printers

    @property
    def hq_workstations(self) -> tuple[HostInfo, ...]:
        return self._hq_workstations

    @property
    def branch_workstations(self) -> tuple[HostInfo, ...]:
        return self._branch_workstations

    def server(self, short: str) -> HostInfo:
        for host in self._servers:
            if short_name(host.hostname) == short:
                return host
        raise KeyError(short)

    def workstations(self, sensor_id: str) -> tuple[HostInfo, ...]:
        if sensor_id == HQ_CORE:
            return self._hq_workstations
        if sensor_id == HARBOR_BRANCH:
            return self._branch_workstations
        return ()

    def services(self, *kinds: str) -> tuple[ExternalService, ...]:
        if not kinds:
            return EXTERNAL_SERVICES
        wanted = frozenset(kinds)
        return tuple(s for s in EXTERNAL_SERVICES if s.kind in wanted)

    def ipv6_services(self) -> tuple[ExternalService, ...]:
        return tuple(s for s in EXTERNAL_SERVICES if s.ipv6)

    def free_ips(self, prefix: str, first: int, last: int) -> Iterator[str]:
        for octet in range(first, last + 1):
            ip = f"{prefix}.{octet}"
            if ip not in self._by_ip:
                yield ip


def _workstation(
    prefix: str, index: int, ip: str, sensor_id: str, user: str, *, with_ipv6: bool = True
) -> HostInfo:
    host_number = HOST_OFFSET + index - 1
    return HostInfo(
        ip=ip,
        hostname=fqdn(f"{prefix}-{index:03d}"),
        kind="internal",
        role="workstation",
        user=user,
        sensor_id=sensor_id,
        ipv6=f"2001:db8:20:4::{host_number:x}" if with_ipv6 else None,
    )
