import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from capture_api.domain.models import ProtocolName
from capture_api.world.catalog import DC_EAST, HARBOR_BRANCH, HQ_CORE
from capture_api.world.filebytes import file_id, file_sha256
from capture_api.world.ids import encode_session_id, minute_index
from capture_api.world.network import (
    BACKUP_HOST,
    VENDOR_UPDATE_HOST,
    Network,
    short_name,
)
from capture_api.world.rng import Stream, stable_int
from capture_api.world.ssh_profiles import SSH_CLIENT_PROFILES, SSH_SERVER_PROFILES
from capture_api.world.tls_profiles import (
    BACKGROUND_CLIENT_PROFILES,
    VENDOR_UPDATER_PROFILE,
    TlsClientProfile,
    server_hello,
    stack_for_host,
)
from capture_api.world.types import (
    AttrValue,
    FileSpec,
    HostInfo,
    Outage,
    Row,
    RowTag,
    SensorInfo,
)
from capture_api.world.users import mailbox

HOUR_MS = 3_600_000
MINUTE_MS = 60_000
BASE_ROWS_PER_HOUR = 625
WEEKEND_FACTOR = 0.4
VOLUME_JITTER = 0.08
EPHEMERAL_LOW, EPHEMERAL_HIGH = 32_768, 60_999
INTEL_SOURCE = "OpenIntel (sim)"

PROTOCOL_ORDER: tuple[ProtocolName, ...] = (
    "dns",
    "tls",
    "http",
    "smb2",
    "smtp",
    "ssh",
    "ntp",
    "tcp",
)

_RAW_OFFICE_CURVE: tuple[float, ...] = (
    0.25,
    0.25,
    0.25,
    0.25,
    0.25,
    0.25,
    0.25,
    0.70,
    1.10,
    1.60,
    1.60,
    1.60,
    1.60,
    1.60,
    1.60,
    1.60,
    1.60,
    1.10,
    0.60,
    0.60,
    0.60,
    0.60,
    0.35,
    0.35,
)
_RAW_DATACENTRE_CURVE: tuple[float, ...] = (
    0.75,
    0.80,
    0.80,
    0.75,
    0.70,
    0.70,
    0.75,
    0.95,
    1.15,
    1.30,
    1.30,
    1.30,
    1.25,
    1.30,
    1.30,
    1.30,
    1.25,
    1.10,
    0.95,
    0.90,
    0.85,
    0.85,
    0.80,
    0.75,
)


def _normalised(curve: Sequence[float]) -> tuple[float, ...]:
    factor = 24.0 / sum(curve)
    return tuple(value * factor for value in curve)


OFFICE_CURVE = _normalised(_RAW_OFFICE_CURVE)
DATACENTRE_CURVE = _normalised(_RAW_DATACENTRE_CURVE)

PROTOCOL_MIX: Mapping[str, tuple[float, ...]] = {
    HQ_CORE: (0.45, 0.33, 0.07, 0.05, 0.02, 0.02, 0.03, 0.03),
    DC_EAST: (0.30, 0.20, 0.05, 0.24, 0.00, 0.11, 0.04, 0.06),
    HARBOR_BRANCH: (0.47, 0.34, 0.08, 0.02, 0.00, 0.01, 0.05, 0.03),
}

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kestrel/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ravenlight/118.2",
    "Mozilla/5.0 (X11; Linux x86_64) Kestrel/121.0",
    "FreightSync/4.2 (+https://erp.example.com)",
    "QuillmereAgent/2.1",
    "curl/8.6.0",
    "Wget/1.21.4",
)
RARE_USER_AGENTS: tuple[str, ...] = (
    "HarvestBot/0.4",
    "libfetch/1.0",
    "Toolkit/0.1 (compatible)",
    "curl/7.29.0",
)
PRINTER_USER_AGENT = "PrintMon/3.1"

DNS_TYPE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("A", 0.76),
    ("AAAA", 0.12),
    ("HTTPS", 0.04),
    ("MX", 0.02),
    ("TXT", 0.02),
    ("PTR", 0.02),
    ("SRV", 0.02),
)
DNS_TTLS: tuple[int, ...] = (60, 120, 300, 900, 3600)

CA_ISSUERS: tuple[str, ...] = (
    "Example Trust Services CA",
    "Example Root CA G2",
    "Fernhollow Internal Issuing CA",
)

HTTP_PATHS: tuple[str, ...] = (
    "/",
    "/index.html",
    "/app.js",
    "/static/app.css",
    "/api/v1/status",
    "/api/v1/shipments",
    "/assets/logo.png",
    "/health",
)
DOWNLOAD_PATHS: tuple[tuple[str, str, str], ...] = (
    ("/downloads/tariff-sheet.pdf", "tariff-sheet.pdf", "application/pdf"),
    ("/downloads/manifest.xlsx", "manifest.xlsx", "application/zip"),
    ("/exports/route-plan.pdf", "route-plan.pdf", "application/pdf"),
    ("/media/berth-plan.png", "berth-plan.png", "image/png"),
    ("/downloads/handbook.docx", "handbook.docx", "application/zip"),
)
ODD_FILE_NAME = "..\\Rechnungen/Q3.pdf"
TRAP_FILE_NAME = "manifest-export.zip"

SMB_TREES: tuple[str, ...] = (
    "\\\\FS01\\finance$",
    "\\\\FS01\\shipping$",
    "\\\\FS01\\common",
    "\\\\DC01\\netlogon",
)
SMB_FOLDERS: tuple[str, ...] = (
    "\\Invoices\\2026",
    "\\Manifests",
    "\\Rates\\Q3",
    "\\Reports",
    "\\Templates",
)
SMB_EXTENSIONS: tuple[str, ...] = (".pdf", ".xlsx", ".docx", ".csv")

MAIL_SUBJECTS: tuple[str, ...] = (
    "Frachtbrief 4471 — Bestätigung",
    "Rate sheet for Q3",
    "Delivery window changed",
    "Container release — berth 7",
    "Invoice 20261 attached",
    "Zollanmeldung Referenz 88-201",
)
MAIL_ATTACHMENTS: tuple[tuple[str, str], ...] = (
    ("manifest.pdf", "application/pdf"),
    ("rates-q3.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("Zollanmeldung.pdf", "application/pdf"),
    (
        "Lieferschein.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
)

SCAN_LOCAL_HOURS: tuple[int, ...] = (3, 11, 19)
SCAN_TARGETS = 50
SCAN_PORTS: tuple[int, ...] = (21, 22, 23, 25, 53, 80, 110, 139, 443, 445, 1433, 3306, 3389, 8080)
VENDOR_BEACON_PERIOD_S = 900
VENDOR_BEACON_HOSTS = 40
VENDOR_DETECTING_HOSTS = 8
BACKUP_LOCAL_HOURS: tuple[int, ...] = (1, 2)
BACKUP_SESSIONS_PER_HOUR = 20
BACKUP_BYTES_PER_SESSION = 1_500_000_000

BACKGROUND_DETECTION_RULES: tuple[str, ...] = (
    "cleartext_credentials",
    "rare_user_agent",
    "dns_tunnel_suspected",
)
BACKGROUND_DETECTION_RATE = 0.055
"""Share of background rows that raise a detection: ≈1 per minute across the three sensors."""


@dataclass(slots=True)
class RowDraft:
    start_ms: int
    end_ms: int
    protocol: ProtocolName
    transport: Literal["udp", "tcp"]
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    bytes_up: int
    bytes_down: int
    packets_up: int
    packets_down: int
    risk_score: int
    summary: str
    risk_reasons: tuple[str, ...] = ()
    intel_score: int | None = None
    attrs: dict[str, AttrValue] = field(default_factory=dict)
    files: tuple[FileSpec, ...] = ()
    tag: RowTag | None = None


class ScriptedSource(Protocol):
    def rows_for(self, sensor_id: str, hour_start_ms: int, hour_end_ms: int) -> list[RowDraft]: ...

    def outages(self) -> Sequence[Outage]: ...


def finalise(
    seed: str,
    drafts: Sequence[RowDraft],
    sensor: SensorInfo,
    id_base_ms: int,
) -> tuple[Row, ...]:
    order = sorted(range(len(drafts)), key=lambda i: (drafts[i].start_ms, i))
    rows: list[Row] = []
    current_minute = -1
    ordinal = 0
    for index in order:
        draft = drafts[index]
        minute = minute_index(draft.start_ms, id_base_ms)
        if minute != current_minute:
            current_minute, ordinal = minute, 0
        session_id = encode_session_id(sensor.index, minute, ordinal)
        if draft.files and "smtp.attachment.sha256" in draft.attrs:
            draft.attrs["smtp.attachment.sha256"] = tuple(
                file_sha256(seed, file_id(session_id, position), spec.mime, spec.size)
                for position, spec in enumerate(draft.files)
            )
        rows.append(
            Row(
                id=session_id,
                sensor_id=sensor.id,
                start_ms=draft.start_ms,
                end_ms=draft.end_ms,
                protocol=draft.protocol,
                transport=draft.transport,
                src_ip=draft.src_ip,
                src_port=draft.src_port,
                dst_ip=draft.dst_ip,
                dst_port=draft.dst_port,
                bytes_up=draft.bytes_up,
                bytes_down=draft.bytes_down,
                packets_up=draft.packets_up,
                packets_down=draft.packets_down,
                risk_score=draft.risk_score,
                risk_reasons=draft.risk_reasons,
                summary=draft.summary,
                intel_score=draft.intel_score,
                attrs=draft.attrs,
                files=draft.files,
                tag=draft.tag,
            )
        )
        ordinal += 1
    return tuple(rows)


def volume(curve: Sequence[float], local_hour: int, weekday: int, stream: Stream) -> int:
    factor = curve[local_hour] * (WEEKEND_FACTOR if weekday >= 5 else 1.0)
    scaled = BASE_ROWS_PER_HOUR * factor * (1.0 + stream.uniform(-VOLUME_JITTER, VOLUME_JITTER))
    return max(1, int(scaled))


def log_int(stream: Stream, low: int, high: int) -> int:
    return max(low, min(high, int(math.exp(stream.uniform(math.log(low), math.log(high + 1))))))


def packets_for(payload: int, *, overhead: int = 3, mtu: int = 1400) -> int:
    return overhead + payload // mtu


def pick_index(stream: Stream, cumulative: Sequence[float]) -> int:
    target = stream.random() * cumulative[-1]
    for index, edge in enumerate(cumulative):
        if target < edge:
            return index
    return len(cumulative) - 1


def _cumulative(weights: Iterable[float]) -> tuple[float, ...]:
    total = 0.0
    edges: list[float] = []
    for weight in weights:
        total += weight
        edges.append(total)
    return tuple(edges)


_DNS_TYPES = tuple(name for name, _ in DNS_TYPE_WEIGHTS)
_DNS_TYPE_EDGES = _cumulative(weight for _, weight in DNS_TYPE_WEIGHTS)


@dataclass(frozen=True, slots=True)
class SensorProfile:
    sensor: SensorInfo
    zone: ZoneInfo
    curve: tuple[float, ...]
    protocol_edges: tuple[float, ...]
    sources: tuple[HostInfo, ...]
    """Hosts that originate traffic on this sensor."""
    ipv6_share: float = 0.0


class BackgroundGenerator:
    __slots__ = (
        "_id_base_ms",
        "_net",
        "_odd_name_slot",
        "_profiles",
        "_scripted",
        "_seed",
        "_trap_slot",
        "_vendor_detectors",
        "_vendor_hosts",
    )

    def __init__(
        self,
        seed: str,
        network: Network,
        sensors: Sequence[SensorInfo],
        *,
        id_base_ms: int,
        epoch_ms: int,
        scripted: ScriptedSource | None = None,
    ) -> None:
        self._seed = seed
        self._net = network
        self._id_base_ms = id_base_ms
        self._scripted = scripted
        self._profiles = {s.id: _profile_for(network, s) for s in sensors if s.id in PROTOCOL_MIX}
        self._vendor_hosts = tuple(
            sorted(
                network.hq_workstations,
                key=lambda h: stable_int(seed, "vendor-host", h.ip),
            )[:VENDOR_BEACON_HOSTS]
        )
        self._vendor_detectors = frozenset(
            host.ip for host in self._vendor_hosts[:VENDOR_DETECTING_HOSTS]
        )
        slots = Stream(seed, "seeded-files")
        first_hour = (epoch_ms - 72 * HOUR_MS - id_base_ms) // HOUR_MS
        self._trap_slot = (HQ_CORE, first_hour + slots.randint(10, 60))
        self._odd_name_slot = (HARBOR_BRANCH, first_hour + slots.randint(10, 60))

    def sensor_ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def block(self, sensor_id: str, hour_index: int) -> tuple[Row, ...]:
        profile = self._profiles.get(sensor_id)
        if profile is None:
            return ()
        hour_start = self._id_base_ms + hour_index * HOUR_MS
        hour_end = hour_start + HOUR_MS
        stream = Stream(self._seed, "block", sensor_id, hour_index)
        local = datetime.fromtimestamp(hour_start / 1000, UTC).astimezone(profile.zone)
        count = volume(profile.curve, local.hour, local.weekday(), stream)
        drafts = [self._row(stream, profile, hour_start) for _ in range(count)]
        self._mark_detections(drafts, stream)
        self._add_herrings(drafts, profile, local.hour, hour_start)
        self._seed_special_files(sensor_id, hour_index, drafts)
        if self._scripted is not None:
            drafts.extend(self._scripted.rows_for(sensor_id, hour_start, hour_end))
            drafts = _outside_outages(drafts, sensor_id, self._scripted.outages())
        _clamp_to_hour(drafts, hour_start, hour_end)
        return finalise(self._seed, drafts, profile.sensor, self._id_base_ms)

    def _row(self, stream: Stream, profile: SensorProfile, hour_start: int) -> RowDraft:
        protocol = PROTOCOL_ORDER[pick_index(stream, profile.protocol_edges)]
        start = hour_start + stream.randbelow(HOUR_MS)
        return _MAKERS[protocol](self, stream, profile, start)

    def _source(self, stream: Stream, profile: SensorProfile) -> HostInfo:
        return stream.choice(profile.sources)

    def _client_profile(self, host: HostInfo, stream: Stream) -> tuple[TlsClientProfile, bool]:
        index = stable_int(self._seed, "stack", host.ip) % len(BACKGROUND_CLIENT_PROFILES)
        if stream.chance(0.08):
            other = (index + 1 + stream.randbelow(len(BACKGROUND_CLIENT_PROFILES) - 1)) % len(
                BACKGROUND_CLIENT_PROFILES
            )
            return BACKGROUND_CLIENT_PROFILES[other], True
        return BACKGROUND_CLIENT_PROFILES[index], False

    def _make_dns(self, stream: Stream, profile: SensorProfile, start: int) -> RowDraft:
        source = self._source(stream, profile)
        qtype = _DNS_TYPES[pick_index(stream, _DNS_TYPE_EDGES)]
        name, answers, ttl, rcode = self._dns_answer(stream, qtype)
        over_ipv6 = source.ipv6 is not None and stream.chance(profile.ipv6_share)
        src_ip = source.ipv6 if over_ipv6 and source.ipv6 else source.ip
        dst_ip = self._net.resolver.ipv6 if over_ipv6 else self._net.resolver.ip
        duration = stream.randint(1, 45)
        up = stream.randint(58, 110)
        down = up + (stream.randint(20, 180) if rcode == "NOERROR" else stream.randint(0, 30))
        summary = (
            f"{qtype} {name} → {answers[0]}"
            if rcode == "NOERROR" and answers
            else f"{rcode} {name}"
        )
        attrs: dict[str, AttrValue] = {
            "dns.query.name": name,
            "dns.query.type": qtype,
            "dns.rcode": rcode,
            "dns.answer": answers,
            "dns.ttl": ttl,
        }
        reasons = ("nxdomain_burst",) if rcode == "NXDOMAIN" and stream.chance(0.2) else ()
        return RowDraft(
            start_ms=start,
            end_ms=start + duration,
            protocol="dns",
            transport="udp",
            src_ip=src_ip or source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=dst_ip or self._net.resolver.ip,
            dst_port=53,
            bytes_up=up,
            bytes_down=down,
            packets_up=1,
            packets_down=1,
            risk_score=_risk(stream, reasons),
            risk_reasons=reasons,
            summary=summary,
            attrs=attrs,
        )

    def _dns_answer(self, stream: Stream, qtype: str) -> tuple[str, tuple[str, ...], int, str]:
        roll = stream.random()
        ttl = stream.choice(DNS_TTLS)
        if roll < 0.04:
            service = stream.choice(self._net.services())
            name = f"{stream.hex(8)}.{service.domain}"
            return name, (), 60, "NXDOMAIN"
        if roll < 0.055:
            service = stream.choice(self._net.services())
            return service.domain, (), 30, "SERVFAIL"
        if roll < 0.20:
            host = stream.choice(self._net.servers + self._net.printers)
            return (host.hostname or host.ip), (host.ip,), 3600, "NOERROR"
        service = stream.choice(self._net.services())
        if qtype == "AAAA":
            answer: tuple[str, ...] = (service.ipv6,) if service.ipv6 else ()
            return service.domain, answer, ttl, "NOERROR"
        if qtype in {"MX", "TXT", "SRV", "PTR"}:
            return service.domain, (f"{qtype.lower()}.{service.domain}",), ttl, "NOERROR"
        return service.domain, (stream.choice(service.ips),), ttl, "NOERROR"

    def _make_tls(self, stream: Stream, profile: SensorProfile, start: int) -> RowDraft:
        source = self._source(stream, profile)
        service = stream.choice(tuple(s for s in self._net.services() if s.tls))
        client, unusual = self._client_profile(source, stream)
        server = server_hello(client, stack_for_host(self._seed, service.domain))
        over_ipv6 = (
            service.ipv6 is not None
            and stream.chance(profile.ipv6_share)
            and source.ipv6 is not None
        )
        dst_ip = service.ipv6 if over_ipv6 and service.ipv6 else stream.choice(service.ips)
        src_ip = source.ipv6 if over_ipv6 and source.ipv6 else source.ip
        up = log_int(stream, 900, 40_000)
        down = log_int(stream, 3_000, 900_000)
        duration = log_int(stream, 60, 40_000)
        reasons: list[str] = []
        if unusual:
            reasons.append("new_ja3_for_host")
        if duration > 20_000:
            reasons.append("long_duration")
        issuer = CA_ISSUERS[stable_int(self._seed, "issuer", service.domain) % len(CA_ISSUERS)]
        return RowDraft(
            start_ms=start,
            end_ms=start + duration,
            protocol="tls",
            transport="tcp",
            src_ip=src_ip or source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=dst_ip,
            dst_port=443,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up, overhead=6),
            packets_down=packets_for(down, overhead=6),
            risk_score=_risk(stream, tuple(reasons)),
            risk_reasons=tuple(reasons),
            summary=f"{server.version_name} {service.domain}",
            intel_score=_intel(stream),
            attrs={
                "tls.sni": service.domain,
                "tls.ja3": client.ja3,
                "tls.version": server.version_name,
                "tls.cert_cn": service.domain,
                "tls.cert_issuer": issuer,
            },
        )

    def _make_http(self, stream: Stream, profile: SensorProfile, start: int) -> RowDraft:
        source = self._source(stream, profile)
        if profile.sensor.id == HQ_CORE and stream.chance(0.35):
            return self._printer_http(stream, source, start)
        service = stream.choice(self._net.services())
        download = stream.choice(DOWNLOAD_PATHS) if stream.chance(0.07) else None
        path = download[0] if download else stream.choice(HTTP_PATHS)
        method = "GET" if stream.chance(0.85) else stream.choice(("POST", "HEAD"))
        status = 200 if stream.chance(0.93) else stream.choice((204, 301, 304, 404, 500))
        agent = stream.choice(USER_AGENTS)
        down = log_int(stream, 400, 400_000) if status == 200 else stream.randint(120, 900)
        up = stream.randint(300, 1_800)
        specs: tuple[FileSpec, ...] = ()
        if download is not None and status == 200 and method == "GET":
            size = log_int(stream, 24_000, 1_800_000)
            down = size + stream.randint(200, 900)
            specs = (
                FileSpec(
                    name=download[1],
                    mime=download[2],
                    size=size,
                    source="http_body",
                    purged=stream.chance(0.03),
                ),
            )
        duration = log_int(stream, 30, 12_000)
        return RowDraft(
            start_ms=start,
            end_ms=start + duration,
            protocol="http",
            transport="tcp",
            src_ip=source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=stream.choice(service.ips),
            dst_port=80,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, ()),
            summary=f"{method} {service.domain}{path} → {status}",
            intel_score=_intel(stream),
            attrs={
                "http.host": service.domain,
                "http.method": method,
                "http.status": status,
                "http.path": path,
                "http.user_agent": agent,
            },
            files=specs,
        )

    def _printer_http(self, stream: Stream, source: HostInfo, start: int) -> RowDraft:
        printer = stream.choice(self._net.printers)
        status = 200 if stream.chance(0.8) else 401
        path = stream.choice(("/status.html", "/admin/queue", "/hp/device/info"))
        reasons = ("cleartext_auth",)
        up = stream.randint(320, 700)
        down = stream.randint(400, 9_000)
        duration = stream.randint(4, 900)
        return RowDraft(
            start_ms=start,
            end_ms=start + duration,
            protocol="http",
            transport="tcp",
            src_ip=source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=printer.ip,
            dst_port=80,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, reasons),
            risk_reasons=reasons,
            summary=f"GET {short_name(printer.hostname)}{path} → {status}",
            attrs={
                "http.host": short_name(printer.hostname) or printer.ip,
                "http.method": "GET",
                "http.status": status,
                "http.path": path,
                "http.user_agent": PRINTER_USER_AGENT,
            },
        )

    def _make_smtp(self, stream: Stream, _profile: SensorProfile, start: int) -> RowDraft:
        gateway = self._net.mail_gateway
        recipient = mailbox(stream.choice(self._net.hq_workstations).user or "post.room")
        inbound = stream.chance(0.6)
        if inbound:
            service = stream.choice(self._net.services("mail", "saas", "payments", "logistics"))
            local = stream.choice(("billing", "orders", "noreply", "support"))
            sender = f"{local}@{service.domain}"
            src_ip, dst_ip, dst_port = stream.choice(service.ips), gateway.ip, 25
        else:
            source = stream.choice(self._net.hq_workstations)
            sender = mailbox(source.user or "post.room")
            recipient = f"desk@{stream.choice(self._net.services('logistics')).domain}"
            src_ip, dst_ip, dst_port = source.ip, gateway.ip, 587
        subject = stream.choice(MAIL_SUBJECTS)
        specs, hashes = self._attachment(stream, start)
        up = stream.randint(2_400, 14_000) + sum(spec.size for spec in specs)
        down = stream.randint(400, 1_200)
        attrs: dict[str, AttrValue] = {
            "smtp.mail_from": sender,
            "smtp.rcpt_to": (recipient,),
            "smtp.subject": subject,
        }
        if hashes:
            attrs["smtp.attachment.sha256"] = hashes
        return RowDraft(
            start_ms=start,
            end_ms=start + stream.randint(200, 9_000),
            protocol="smtp",
            transport="tcp",
            src_ip=src_ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=dst_ip,
            dst_port=dst_port,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, ()),
            summary=f"SMTP {sender} → {recipient} ({_attachment_phrase(len(specs))})",
            attrs=attrs,
            files=specs,
        )

    def _attachment(
        self, stream: Stream, start: int
    ) -> tuple[tuple[FileSpec, ...], tuple[str, ...]]:
        if not stream.chance(0.25):
            return (), ()
        name, mime = stream.choice(MAIL_ATTACHMENTS)
        spec = FileSpec(
            name=name,
            mime=mime,
            size=log_int(stream, 18_000, 260_000),
            source="smtp_attachment",
            purged=stream.chance(0.03),
        )
        placeholder = file_id(start, 0)
        return (spec,), (file_sha256(self._seed, placeholder, spec.mime, spec.size),)

    def _make_smb2(self, stream: Stream, _profile: SensorProfile, start: int) -> RowDraft:
        source = stream.choice(self._net.hq_workstations)
        tree = stream.choice(SMB_TREES)
        server_short = tree.strip("\\").split("\\")[0].lower()
        server = self._net.server(server_short)
        folder = stream.choice(SMB_FOLDERS)
        path = f"{folder}\\{stream.hex(6)}{stream.choice(SMB_EXTENSIONS)}"
        denied = stream.chance(0.02)
        status = "STATUS_ACCESS_DENIED" if denied else "STATUS_SUCCESS"
        down = max(200, 0 if denied else log_int(stream, 4_000, 6_000_000))
        up = stream.randint(700, 3_000)
        summary = f"SMB2 TREE_CONNECT {tree}" if denied else f"SMB2 READ {tree}{path}"
        return RowDraft(
            start_ms=start,
            end_ms=start + log_int(stream, 40, 20_000),
            protocol="smb2",
            transport="tcp",
            src_ip=source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=server.ip,
            dst_port=445,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, ()),
            summary=summary,
            attrs={
                "smb2.tree": tree,
                "smb2.path": (path,),
                "smb2.status": status,
            },
        )

    def _make_ssh(self, stream: Stream, _profile: SensorProfile, start: int) -> RowDraft:
        source = stream.choice(self._net.hq_workstations)
        target = self._net.server(stream.choice(("jump01", "app01")))
        client = stream.choice(SSH_CLIENT_PROFILES)
        server = SSH_SERVER_PROFILES[stable_int(self._seed, "ssh", target.ip) % 2]
        duration = log_int(stream, 2_000, 900_000)
        up = log_int(stream, 3_000, 400_000)
        down = log_int(stream, 6_000, 2_000_000)
        reasons = ("long_duration",) if duration > 600_000 else ()
        return RowDraft(
            start_ms=start,
            end_ms=start + duration,
            protocol="ssh",
            transport="tcp",
            src_ip=source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=target.ip,
            dst_port=22,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, reasons),
            risk_reasons=reasons,
            summary=f"{client.version} → {short_name(target.hostname)}",
            attrs={"ssh.hassh": client.hassh, "ssh.server_version": server.version},
        )

    def _make_ntp(self, stream: Stream, profile: SensorProfile, start: int) -> RowDraft:
        source = self._source(stream, profile)
        service = stream.choice(self._net.services("ntp"))
        return RowDraft(
            start_ms=start,
            end_ms=start + stream.randint(2, 60),
            protocol="ntp",
            transport="udp",
            src_ip=source.ip,
            src_port=123,
            dst_ip=stream.choice(service.ips),
            dst_port=123,
            bytes_up=90,
            bytes_down=90,
            packets_up=1,
            packets_down=1,
            risk_score=stream.randbelow(6),
            summary=f"NTP client → {service.domain}",
        )

    def _make_tcp(self, stream: Stream, profile: SensorProfile, start: int) -> RowDraft:
        source = self._source(stream, profile)
        service = stream.choice(self._net.services())
        port = stream.choice((8080, 8443, 5222, 1194, 9418, 3128))
        up = log_int(stream, 200, 60_000)
        down = log_int(stream, 200, 200_000)
        dst_ip = stream.choice(service.ips)
        return RowDraft(
            start_ms=start,
            end_ms=start + log_int(stream, 20, 60_000),
            protocol="tcp",
            transport="tcp",
            src_ip=source.ip,
            src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
            dst_ip=dst_ip,
            dst_port=port,
            bytes_up=up,
            bytes_down=down,
            packets_up=packets_for(up),
            packets_down=packets_for(down),
            risk_score=_risk(stream, ()),
            summary=f"TCP {source.ip}:{port} → {dst_ip}:{port}",
            intel_score=_intel(stream),
        )

    def _add_herrings(
        self, drafts: list[RowDraft], profile: SensorProfile, local_hour: int, hour_start: int
    ) -> None:
        if profile.sensor.id == HQ_CORE:
            if local_hour in SCAN_LOCAL_HOURS:
                drafts.extend(self._port_scan(hour_start))
            drafts.extend(self._vendor_beacons(hour_start))
        elif profile.sensor.id == DC_EAST and local_hour in BACKUP_LOCAL_HOURS:
            drafts.extend(self._nightly_backup(hour_start))

    def _port_scan(self, hour_start: int) -> list[RowDraft]:
        stream = Stream(self._seed, "scan", hour_start)
        scanner = self._net.scanner
        targets = stream.sample(
            self._net.hq_workstations + self._net.printers + self._net.servers, SCAN_TARGETS
        )
        begin = hour_start + stream.randbelow(40 * MINUTE_MS)
        drafts: list[RowDraft] = []
        for position, target in enumerate(targets):
            ports = stream.sample(SCAN_PORTS, stream.randint(6, 10))
            for index, port in enumerate(ports):
                offset = position * 4_000 + index * 180 + stream.randbelow(120)
                open_port = port in {80, 443, 445, 22}
                draft = RowDraft(
                    start_ms=begin + offset,
                    end_ms=begin + offset + stream.randint(1, 30),
                    protocol="tcp",
                    transport="tcp",
                    src_ip=scanner.ip,
                    src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                    dst_ip=target.ip,
                    dst_port=port,
                    bytes_up=74,
                    bytes_down=74 if open_port else 54,
                    packets_up=1,
                    packets_down=1,
                    risk_score=stream.randint(70, 86),
                    risk_reasons=("port_scan",),
                    summary=f"TCP SYN scan {scanner.ip} → {target.ip}:{port}",
                    tag="herring.scan",
                )
                if index == 0:
                    draft.attrs["detection.rule"] = ("port_scan",)
                drafts.append(draft)
        return drafts

    def _vendor_beacons(self, hour_start: int) -> list[RowDraft]:
        service = self._net.service(VENDOR_UPDATE_HOST)
        if service is None:
            return []
        stream = Stream(self._seed, "vendor", hour_start)
        drafts: list[RowDraft] = []
        period_ms = VENDOR_BEACON_PERIOD_S * 1000
        for host in self._vendor_hosts:
            anchor = stable_int(self._seed, "vendor-offset", host.ip) % period_ms
            first = hour_start + (anchor - hour_start) % period_ms
            for tick in range(first, hour_start + HOUR_MS, period_ms):
                index = (tick - anchor) // period_ms
                up = stream.randint(820, 1_150)
                down = stream.randint(2_200, 3_600)
                draft = RowDraft(
                    start_ms=tick + stream.randbelow(1_500),
                    end_ms=tick + stream.randint(700, 2_600),
                    protocol="tls",
                    transport="tcp",
                    src_ip=host.ip,
                    src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                    dst_ip=service.ips[0],
                    dst_port=443,
                    bytes_up=up,
                    bytes_down=down,
                    packets_up=packets_for(up, overhead=6),
                    packets_down=packets_for(down, overhead=6),
                    risk_score=stream.randint(18, 34),
                    summary=f"TLS1.2 {service.domain}",
                    attrs={
                        "tls.sni": service.domain,
                        "tls.ja3": VENDOR_UPDATER_PROFILE.ja3,
                        "tls.version": "TLS1.2",
                        "tls.cert_cn": service.domain,
                        "tls.cert_issuer": CA_ISSUERS[0],
                    },
                    tag="herring.vendor",
                )
                if host.ip in self._vendor_detectors and index % 2 == 0:
                    draft.attrs["detection.rule"] = ("periodic_tls_beacon",)
                drafts.append(draft)
        return drafts

    def _nightly_backup(self, hour_start: int) -> list[RowDraft]:
        service = self._net.service(BACKUP_HOST)
        if service is None:
            return []
        stream = Stream(self._seed, "backup", hour_start)
        source = self._net.server("bkp01")
        drafts: list[RowDraft] = []
        step = HOUR_MS // BACKUP_SESSIONS_PER_HOUR
        for index in range(BACKUP_SESSIONS_PER_HOUR):
            start = hour_start + index * step + stream.randbelow(step // 2)
            up = int(stream.jitter(BACKUP_BYTES_PER_SESSION, 0.18))
            down = stream.randint(40_000, 260_000)
            drafts.append(
                RowDraft(
                    start_ms=start,
                    end_ms=start + stream.randint(90_000, 165_000),
                    protocol="tls",
                    transport="tcp",
                    src_ip=source.ip,
                    src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
                    dst_ip=stream.choice(service.ips),
                    dst_port=443,
                    bytes_up=up,
                    bytes_down=down,
                    packets_up=packets_for(up, overhead=12),
                    packets_down=packets_for(down, overhead=12),
                    risk_score=stream.randint(34, 48),
                    risk_reasons=("high_volume_out",),
                    summary=f"TLS1.3 {service.domain} (nightly backup)",
                    attrs={
                        "tls.sni": service.domain,
                        "tls.ja3": BACKGROUND_CLIENT_PROFILES[4].ja3,
                        "tls.version": "TLS1.3",
                        "tls.cert_cn": service.domain,
                        "tls.cert_issuer": CA_ISSUERS[0],
                    },
                    tag="herring.backup",
                )
            )
        return drafts

    def _mark_detections(self, drafts: Sequence[RowDraft], stream: Stream) -> None:
        pools: dict[str, list[RowDraft]] = {
            rule: [d for d in drafts if _eligible(d, rule)] for rule in BACKGROUND_DETECTION_RULES
        }
        available = tuple(rule for rule in BACKGROUND_DETECTION_RULES if pools[rule])
        if not available:
            return
        budget = max(3, round(len(drafts) * BACKGROUND_DETECTION_RATE))
        for _ in range(budget):
            rule = stream.choice(available)
            draft = stream.choice(pools[rule])
            existing = draft.attrs.get("detection.rule")
            rules = tuple(existing) if isinstance(existing, tuple) else ()
            if rule in rules:
                continue
            draft.attrs["detection.rule"] = (*rules, rule)
            if rule == "rare_user_agent":
                agent = stream.choice(RARE_USER_AGENTS)
                draft.attrs["http.user_agent"] = agent
            if rule == "dns_tunnel_suspected":
                name = draft.attrs.get("dns.query.name")
                if isinstance(name, str):
                    draft.attrs["dns.query.name"] = f"{stream.hex(40)}.{name}"

    def _seed_special_files(
        self, sensor_id: str, hour_index: int, drafts: Sequence[RowDraft]
    ) -> None:
        for slot, name, mime, trap in (
            (self._trap_slot, TRAP_FILE_NAME, "application/zip", True),
            (self._odd_name_slot, ODD_FILE_NAME, "application/pdf", False),
        ):
            if slot != (sensor_id, hour_index):
                continue
            target = _download_carrier(drafts)
            if target is None:
                continue
            size = target.files[0].size if target.files else 240_000
            target.attrs["http.status"] = 200
            target.files = (
                FileSpec(name=name, mime=mime, size=size, source="http_body", trap=trap),
            )


def _attachment_phrase(count: int) -> str:
    if count == 0:
        return "no attachments"
    return "1 attachment" if count == 1 else f"{count} attachments"


def _download_carrier(drafts: Sequence[RowDraft]) -> RowDraft | None:
    carrier = next((d for d in drafts if d.files and d.files[0].source == "http_body"), None)
    if carrier is not None:
        return carrier
    return next(
        (d for d in drafts if d.protocol == "http" and d.attrs.get("http.method") == "GET"),
        None,
    )


def _clamp_to_hour(drafts: Sequence[RowDraft], hour_start: int, hour_end: int) -> None:
    for draft in drafts:
        clamped = min(max(draft.start_ms, hour_start), hour_end - 1)
        if clamped != draft.start_ms:
            draft.end_ms += clamped - draft.start_ms
            draft.start_ms = clamped


def _eligible(draft: RowDraft, rule: str) -> bool:
    if rule == "cleartext_credentials":
        return draft.protocol == "http" and "cleartext_auth" in draft.risk_reasons
    if rule == "rare_user_agent":
        return draft.protocol == "http" and draft.tag is None
    return draft.protocol == "dns" and draft.attrs.get("dns.rcode") == "NOERROR"


def _risk(stream: Stream, reasons: Sequence[str]) -> int:
    score = stream.randbelow(19)
    for reason in reasons:
        score += _REASON_POINTS.get(reason, 10)
    return min(100, score)


_REASON_POINTS: Mapping[str, int] = {
    "rare_domain": 22,
    "new_ja3_for_host": 26,
    "cleartext_auth": 24,
    "long_duration": 14,
    "high_volume_out": 30,
    "nxdomain_burst": 18,
    "self_signed_cert": 30,
    "cn_mismatch": 28,
    "port_scan": 60,
    "lookalike_domain": 45,
    "smb_mass_read": 45,
}


def _intel(stream: Stream) -> int | None:
    return stream.randint(10, 92) if stream.chance(0.02) else None


def _outside_outages(
    drafts: Sequence[RowDraft], sensor_id: str, outages: Sequence[Outage]
) -> list[RowDraft]:
    windows = [(o.start_ms, o.end_ms) for o in outages if o.sensor_id == sensor_id]
    if not windows:
        return list(drafts)
    return [
        draft
        for draft in drafts
        if not any(start <= draft.start_ms < end for start, end in windows)
    ]


def _profile_for(network: Network, sensor: SensorInfo) -> SensorProfile:
    if sensor.id == DC_EAST:
        sources: tuple[HostInfo, ...] = network.servers
        curve = DATACENTRE_CURVE
        ipv6_share = 0.0
    elif sensor.id == HQ_CORE:
        sources = (*network.hq_workstations, *network.printers, network.mail_gateway)
        curve = OFFICE_CURVE
        ipv6_share = 0.03
    else:
        sources = network.branch_workstations
        curve = OFFICE_CURVE
        ipv6_share = 0.0
    return SensorProfile(
        sensor=sensor,
        zone=ZoneInfo(sensor.tz),
        curve=curve,
        protocol_edges=_cumulative(PROTOCOL_MIX[sensor.id]),
        sources=sources,
        ipv6_share=ipv6_share,
    )


_MAKERS: Mapping[str, Callable[[BackgroundGenerator, Stream, SensorProfile, int], RowDraft]] = {
    "dns": BackgroundGenerator._make_dns,
    "tls": BackgroundGenerator._make_tls,
    "http": BackgroundGenerator._make_http,
    "smb2": BackgroundGenerator._make_smb2,
    "smtp": BackgroundGenerator._make_smtp,
    "ssh": BackgroundGenerator._make_ssh,
    "ntp": BackgroundGenerator._make_ntp,
    "tcp": BackgroundGenerator._make_tcp,
}
