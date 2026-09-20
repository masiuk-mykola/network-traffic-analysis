from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from capture_api.domain.models import ColumnDef, FieldDef, FieldType, FilterOp
from capture_api.world.types import SensorInfo

HQ_CORE = "hq-core"
DC_EAST = "dc-east"
HARBOR_BRANCH = "harbor-branch"

BUILTIN_SENSORS: tuple[SensorInfo, ...] = (
    SensorInfo(
        id=HQ_CORE,
        index=1,
        name="HQ Core",
        site="Lisbon HQ",
        kind="tap",
        tz="Europe/Lisbon",
        decoder_version="v2",
        status="online",
        lag_s=2,
    ),
    SensorInfo(
        id=DC_EAST,
        index=2,
        name="DC East",
        site="Lisbon DC",
        kind="span",
        tz="Europe/Lisbon",
        decoder_version="v2",
        status="online",
        lag_s=1,
    ),
    SensorInfo(
        id=HARBOR_BRANCH,
        index=3,
        name="Hafenbüro Nord",
        site="Hamburg Branch",
        kind="tap",
        tz="Europe/Berlin",
        decoder_version="v1",
        status="lagging",
        lag_s=300,
    ),
)
"""The three built-in sensors in index order. Imports get index 16 and up."""

BUILTIN_SENSOR_IDS: tuple[str, ...] = tuple(s.id for s in BUILTIN_SENSORS)
FIRST_IMPORT_SENSOR_INDEX = 16

PROTOCOLS: tuple[tuple[str, str], ...] = (
    ("dns", "DNS"),
    ("http", "HTTP"),
    ("tls", "TLS"),
    ("smtp", "SMTP"),
    ("smb2", "SMB2"),
    ("ssh", "SSH"),
    ("ntp", "NTP"),
    ("tcp", "Other TCP"),
)


@dataclass(frozen=True, slots=True)
class DetectionRule:
    rule_id: str
    name: str
    severity: str
    technique_id: str
    technique_name: str


DETECTION_RULES: Mapping[str, DetectionRule] = {
    rule.rule_id: rule
    for rule in (
        DetectionRule(
            "periodic_tls_beacon",
            "Periodic TLS beacon",
            "high",
            "T1071.001",
            "Application Layer Protocol: Web Protocols",
        ),
        DetectionRule(
            "lookalike_sender",
            "Look-alike sender domain",
            "medium",
            "T1566.001",
            "Phishing: Spearphishing Attachment",
        ),
        DetectionRule(
            "smb_mass_read",
            "Mass file read from a network share",
            "high",
            "T1039",
            "Data from Network Shared Drive",
        ),
        DetectionRule(
            "port_scan",
            "Port scan",
            "high",
            "T1046",
            "Network Service Discovery",
        ),
        DetectionRule(
            "dns_tunnel_suspected",
            "Suspected DNS tunnelling",
            "medium",
            "T1071.004",
            "Application Layer Protocol: DNS",
        ),
        DetectionRule(
            "cleartext_credentials",
            "Clear-text credentials",
            "medium",
            "T1552",
            "Unsecured Credentials",
        ),
        DetectionRule(
            "rare_user_agent",
            "Rare HTTP user agent",
            "low",
            "T1071.001",
            "Application Layer Protocol: Web Protocols",
        ),
    )
}


@dataclass(frozen=True, slots=True)
class RiskReasonDef:
    code: str
    label: str
    mitre: str | None = None


RISK_REASONS: Mapping[str, RiskReasonDef] = {
    reason.code: reason
    for reason in (
        RiskReasonDef("rare_domain", "Rarely seen domain"),
        RiskReasonDef("new_ja3_for_host", "New TLS client fingerprint for this host", "T1071.001"),
        RiskReasonDef("cleartext_auth", "Clear-text authentication", "T1552"),
        RiskReasonDef("long_duration", "Unusually long session"),
        RiskReasonDef("high_volume_out", "High outbound volume", "T1048"),
        RiskReasonDef("nxdomain_burst", "Burst of NXDOMAIN answers", "T1568.002"),
        RiskReasonDef("self_signed_cert", "Self-signed certificate"),
        RiskReasonDef("cn_mismatch", "Certificate name does not match SNI"),
        RiskReasonDef("port_scan", "Port-scan pattern", "T1046"),
        RiskReasonDef("lookalike_domain", "Look-alike domain", "T1566.001"),
        RiskReasonDef("smb_mass_read", "Mass read from a file share", "T1039"),
    )
}


def risk_band(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


COUNTRIES: Mapping[str, str] = {
    "PT": "Portugal",
    "DE": "Germany",
    "US": "United States",
    "NL": "Netherlands",
    "FR": "France",
    "GB": "United Kingdom",
    "SE": "Sweden",
    "PL": "Poland",
    "IE": "Ireland",
    "ES": "Spain",
    "CA": "Canada",
    "JP": "Japan",
    "SG": "Singapore",
    "BR": "Brazil",
    "CH": "Switzerland",
    "AT": "Austria",
}
"""The external-country pool (ISO alpha-2 → name), assigned per /26 by the world."""

DNS_QUERY_TYPES: Mapping[str, int] = {
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

DNS_RCODES: Mapping[str, int] = {
    "NOERROR": 0,
    "FORMERR": 1,
    "SERVFAIL": 2,
    "NXDOMAIN": 3,
    "NOTIMP": 4,
    "REFUSED": 5,
}

HTTP_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH")

TLS_VERSIONS: tuple[tuple[str, str], ...] = (
    ("TLS1.0", "TLS 1.0"),
    ("TLS1.1", "TLS 1.1"),
    ("TLS1.2", "TLS 1.2"),
    ("TLS1.3", "TLS 1.3"),
)

SMB2_STATUSES: Mapping[str, int] = {
    "STATUS_SUCCESS": 0x00000000,
    "STATUS_PENDING": 0x00000103,
    "STATUS_END_OF_FILE": 0xC0000011,
    "STATUS_ACCESS_DENIED": 0xC0000022,
    "STATUS_OBJECT_NAME_NOT_FOUND": 0xC0000034,
    "STATUS_LOGON_FAILURE": 0xC000006D,
    "STATUS_BAD_NETWORK_NAME": 0xC00000CC,
}

RISK_BANDS: tuple[tuple[str, str], ...] = (("low", "Low"), ("medium", "Medium"), ("high", "High"))

ENUM_NAMES: tuple[str, ...] = (
    "protocol",
    "country",
    "risk_band",
    "detection_rule",
    "dns_query_type",
    "dns_rcode",
    "http_method",
    "tls_version",
    "smb2_status",
)


def enum_values(name: str) -> list[tuple[str, str]] | None:
    tables: dict[str, list[tuple[str, str]]] = {
        "protocol": list(PROTOCOLS),
        "country": sorted(COUNTRIES.items(), key=lambda kv: kv[1]),
        "risk_band": list(RISK_BANDS),
        "detection_rule": [(r.rule_id, r.name) for r in DETECTION_RULES.values()],
        "dns_query_type": [(k, k) for k in DNS_QUERY_TYPES],
        "dns_rcode": [(k, k) for k in DNS_RCODES],
        "http_method": [(m, m) for m in HTTP_METHODS],
        "tls_version": list(TLS_VERSIONS),
        "smb2_status": [(k, k) for k in SMB2_STATUSES],
    }
    return tables.get(name)


def _field(
    name: str,
    label: str,
    type_: FieldType,
    operators: Sequence[FilterOp],
    example: str,
    *,
    enum: Sequence[str] | None = None,
    enum_name: str | None = None,
    pattern: str | None = None,
) -> FieldDef:
    return FieldDef(
        name=name,
        label=label,
        type=type_,
        operators=list(operators),
        enum=list(enum) if enum is not None else None,
        enum_name=enum_name,
        pattern=pattern,
        example=example,
    )


FIELD_DEFS: tuple[FieldDef, ...] = (
    _field("sensor", "Sensor", "sensor", ("eq",), HQ_CORE, enum=BUILTIN_SENSOR_IDS),
    _field(
        "protocol",
        "Protocol",
        "enum",
        ("eq",),
        "tls",
        enum=[p for p, _ in PROTOCOLS],
        enum_name="protocol",
    ),
    _field("src.ip", "Source IP", "ip", ("eq", "cidr", "exists"), "10.20.4.17"),
    _field("dst.ip", "Destination IP", "ip", ("eq", "cidr", "exists"), "203.0.113.24"),
    _field("src.port", "Source port", "port", ("eq", "gte", "lte", "between"), "49312"),
    _field("dst.port", "Destination port", "port", ("eq", "gte", "lte", "between"), "443"),
    _field("host", "Host (either side)", "string", ("eq", "glob", "exists"), "*.example.net"),
    _field("dst.host", "Destination host", "string", ("eq", "glob", "exists"), "cdn.example.net"),
    _field(
        "dst.country",
        "Destination country",
        "country",
        ("eq", "exists"),
        "PT",
        enum=list(COUNTRIES),
        enum_name="country",
    ),
    _field("risk.score", "Risk score", "number", ("gte", "lte", "between"), "70"),
    _field("bytes.up", "Bytes up", "bytes", ("gte", "lte", "between"), "1048576"),
    _field("bytes.down", "Bytes down", "bytes", ("gte", "lte", "between"), "4096"),
    _field("duration_ms", "Duration", "duration_ms", ("gte", "lte", "between"), "30000"),
    _field("dns.query.name", "DNS query name", "string", ("eq", "glob"), "*.example.org"),
    _field(
        "dns.query.type",
        "DNS query type",
        "enum",
        ("eq",),
        "A",
        enum=list(DNS_QUERY_TYPES),
        enum_name="dns_query_type",
    ),
    _field(
        "dns.rcode",
        "DNS rcode",
        "enum",
        ("eq",),
        "NXDOMAIN",
        enum=list(DNS_RCODES),
        enum_name="dns_rcode",
    ),
    _field("http.host", "HTTP host", "string", ("eq", "glob"), "static.example.com"),
    _field(
        "http.method",
        "HTTP method",
        "enum",
        ("eq",),
        "PUT",
        enum=list(HTTP_METHODS),
        enum_name="http_method",
    ),
    _field("http.status", "HTTP status", "number", ("eq", "gte", "lte", "between"), "200"),
    _field("http.user_agent", "HTTP user agent", "string", ("eq", "glob"), "*curl*"),
    _field("tls.sni", "TLS SNI", "string", ("eq", "glob", "exists"), "docs.example.org"),
    _field(
        "tls.ja3",
        "TLS JA3",
        "ja3",
        ("eq",),
        "6f1c3e6b1b5d4a2f8c0d7e9a3b5c1d2e",
        pattern="^[0-9a-f]{32}$",
    ),
    _field(
        "tls.version",
        "TLS version",
        "enum",
        ("eq",),
        "TLS1.2",
        enum=[v for v, _ in TLS_VERSIONS],
        enum_name="tls_version",
    ),
    _field("smtp.mail_from", "SMTP sender", "string", ("eq", "glob"), "billing@*.example"),
    _field(
        "smtp.attachment.sha256",
        "Attachment SHA-256",
        "string",
        ("eq",),
        "9f2c1d0b" + "0" * 56,
        pattern="^[0-9a-fA-F]{64}$",
    ),
    _field("smb2.path", "SMB2 file path", "string", ("eq", "glob"), r"\Reports\*.pdf"),
    _field(
        "smb2.status",
        "SMB2 status",
        "enum",
        ("eq",),
        "STATUS_ACCESS_DENIED",
        enum=list(SMB2_STATUSES),
        enum_name="smb2_status",
    ),
    _field(
        "ssh.hassh",
        "SSH HASSH",
        "string",
        ("eq",),
        "3d2a7c5e9b1f4068a2c4e6d8b0a2c4e6",
        pattern="^[0-9a-f]{32}$",
    ),
    _field(
        "detection.rule",
        "Detection rule",
        "enum",
        ("eq", "exists"),
        "port_scan",
        enum=list(DETECTION_RULES),
        enum_name="detection_rule",
    ),
)
"""The `/v1/meta/fields` catalogue: the contract between the rows' indexed attributes,
the filter compiler and the GET `f` grammar. The `sensor` field's `enum` lists the built-in
sensors; the route extends it with ready imports."""

FIELD_DEFS_BY_NAME: Mapping[str, FieldDef] = {field.name: field for field in FIELD_DEFS}


def _column(
    key: str,
    label: str,
    type_: str,
    *,
    default_visible: bool = True,
    sortable: bool = False,
    width_hint: int = 140,
) -> ColumnDef:
    return ColumnDef(
        key=key,
        label=label,
        type=type_,
        default_visible=default_visible,
        sortable=sortable,
        width_hint=width_hint,
    )


COLUMN_DEFS: tuple[ColumnDef, ...] = (
    _column("start", "Start", "ts", sortable=True, width_hint=190),
    _column("sensor", "Sensor", "sensor", width_hint=130),
    _column("src", "Source", "ip_port", width_hint=190),
    _column("dst", "Destination", "ip_port", width_hint=190),
    _column("protocol", "Protocol", "protocol", width_hint=100),
    _column("summary", "Summary", "text", width_hint=360),
    _column("bytes", "Bytes", "bytes", sortable=True, width_hint=120),
    _column("duration", "Duration", "duration", width_hint=110),
    _column("risk", "Risk", "risk", sortable=True, width_hint=110),
    _column("id", "Session id", "id", default_visible=False, width_hint=190),
    _column("packets", "Packets", "text", default_visible=False, width_hint=110),
    _column("decoder", "Decoder", "text", default_visible=False, width_hint=100),
    _column("files", "Files", "text", default_visible=False, width_hint=80),
    _column("dst_country", "Destination country", "geo_hint", default_visible=False),
)
"""The `/v1/meta/columns` catalogue, in default order. `dst_country` carries the
undocumented `geo_hint` type on purpose: clients must render unknown column types as text."""
