from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from capture_api.domain.base import ms_to_iso
from capture_api.world.tls_profiles import TlsClientProfile

if TYPE_CHECKING:
    from capture_api.domain.models import (
        Detection,
        ProtocolSchema,
        Sensor,
        Session,
        SessionRow,
    )
    from capture_api.world.clock import CaptureClock

type Role = Literal["analyst", "observer"]
type AttrValue = str | int | tuple[str, ...]
type RowTag = Literal[
    "incident.email",
    "incident.first_contact",
    "incident.beacon",
    "incident.smb",
    "incident.smb_denied",
    "incident.exfil",
    "herring.scan",
    "herring.vendor",
    "herring.backup",
]
"""Provenance of scripted rows (``None`` for plain background). Internal; never exposed."""

EMPTY_ATTRS: Mapping[str, AttrValue] = {}


@dataclass(frozen=True, slots=True)
class SensorInfo:
    id: str
    index: int
    name: str
    site: str
    kind: Literal["tap", "span", "import"]
    tz: str
    decoder_version: Literal["v1", "v2"]
    status: Literal["online", "lagging", "offline"]
    lag_s: int
    metadata_days: int = 30
    pcap_hours: int = 48
    files_days: int = 7
    import_id: str | None = None


@dataclass(frozen=True, slots=True)
class HostInfo:
    ip: str
    hostname: str | None
    kind: Literal["internal", "external"]
    role: str
    """``workstation|server|printer|scanner|resolver|mail|service|peer``."""
    country: str | None = None
    """ISO alpha-2 for external addresses; ``None`` internally."""
    user: str | None = None
    """Primary user ``first.last`` of a workstation."""
    sensor_id: str | None = None
    """The sensor that sees this internal host."""
    ipv6: str | None = None


@dataclass(frozen=True, slots=True)
class FileSpec:
    name: str
    mime: str
    size: int
    source: Literal["smtp_attachment", "http_body"]
    purged: bool = False
    trap: bool = False
    """The one file whose download answers 200 ``{"error": "extraction_failed"}``."""


@dataclass(frozen=True, slots=True)
class FileData:
    id: str
    session_id: int
    name: str
    mime: str
    size: int
    sha256: str
    source: Literal["smtp_attachment", "http_body"]
    purged: bool
    trap: bool


@dataclass(frozen=True, slots=True)
class Row:
    id: int
    sensor_id: str
    start_ms: int
    end_ms: int
    protocol: Literal["dns", "http", "tls", "smtp", "smb2", "ssh", "ntp", "tcp"]
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
    risk_reasons: tuple[str, ...]
    """Codes from ``catalog.RISK_REASONS``."""
    summary: str
    intel_score: int | None = None
    attrs: Mapping[str, AttrValue] = field(default_factory=lambda: EMPTY_ATTRS)
    files: tuple[FileSpec, ...] = ()
    tag: RowTag | None = None

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def files_count(self) -> int:
        return len(self.files)

    def attr(self, key: str) -> AttrValue | None:
        return self.attrs.get(key)

    def attr_str(self, key: str) -> str | None:
        value = self.attrs.get(key)
        return value if isinstance(value, str) else None


@dataclass(frozen=True, slots=True)
class Outage:
    sensor_id: str
    start_ms: int
    end_ms: int
    reason: str


@dataclass(frozen=True, slots=True)
class PcapStatus:
    available: bool
    reason: Literal["expired", "not_captured"] | None = None
    expired_at_ms: int | None = None


@dataclass(frozen=True, slots=True)
class DetectionData:
    seq: int
    id: str
    ts_ms: int
    rule_id: str
    """Key into ``catalog.DETECTION_RULES`` (name, severity default, MITRE)."""
    severity: Literal["low", "medium", "high"]
    sensor_id: str
    session_id: int
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    summary: str


@dataclass(frozen=True, slots=True)
class FlowSampleData:
    t_ms: int
    bytes_up: int
    bytes_down: int
    packets_up: int
    packets_down: int


@dataclass(frozen=True, slots=True)
class EnrichData:
    ip: str
    reputation: Literal["clean", "suspicious", "malicious", "unknown"]
    country: str | None = None
    asn: str | None = None
    org: str | None = None


@dataclass(frozen=True, slots=True)
class IncidentParams:
    seed: str
    patient_zero_ip: str
    patient_zero_host: str
    """FQDN, e.g. ``ws-hb-017.quillmere.example``."""
    patient_zero_user: str
    """``first.last``; mailbox ``<user>@quillmere.example``."""
    lookalike_domain: str
    lookalike_sender_ip: str
    c2_domain: str
    """Base domain, e.g. ``cdn-metrics.test``."""
    c2_ip: str
    c2_upload_ip: str
    c2_client_profile: TlsClientProfile
    cert_cn: str
    """Self-signed leaf CN, ``<4 hex>.invalid``."""
    beacon_interval_s: int
    beacon_jitter: float
    email_ms: int
    first_contact_ms: int
    beacon_start_ms: int
    smb_start_ms: int
    exfil_start_ms: int
    exfil_end_ms: int
    smb_file_count: int
    exfil_channel: Literal["https_upload", "http_put"]
    exfil_sessions: int
    exfil_target_bytes: int
    http_put_ip: str
    attachment_name: str
    capture_gap_start_ms: int
    capture_gap_end_ms: int

    @property
    def c2_sni(self) -> str:
        return f"telemetry.{self.c2_domain}"

    @property
    def c2_upload_host(self) -> str:
        return f"upload.{self.c2_domain}"

    @property
    def sender(self) -> str:
        return f"billing@{self.lookalike_domain}"


@dataclass(frozen=True, slots=True)
class Truth:
    seed: str
    patient_zero_ip: str
    patient_zero_host: str
    patient_zero_user: str
    first_c2_session_id: int
    first_c2_start_ms: int
    c2_domain: str
    c2_ip: str
    c2_sni: str
    c2_ja3: str
    lookalike_domain: str
    attachment_name: str
    attachment_sha256: str
    email_session_id: int
    smb_tree: str
    smb_file_count: int
    denied_share: str
    exfil_channel: Literal["https_upload", "http_put"]
    exfil_start_ms: int
    exfil_end_ms: int
    exfil_bytes_up: int
    exfil_session_count: int
    q6_session_id: int
    q6_pcap_sha256: str
    twelfth_beacon_session_id: int
    capture_gap_start_ms: int
    capture_gap_end_ms: int

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name.endswith("session_id"):
                out[name] = str(value)
            elif name.endswith("_ms"):
                out[name] = value
                out[name.removesuffix("_ms")] = ms_to_iso(value)
            else:
                out[name] = value
        return out


class DecodeContext(Protocol):
    @property
    def seed(self) -> str: ...

    @property
    def epoch_ms(self) -> int: ...

    def sensor(self, sensor_id: str) -> SensorInfo | None: ...

    def host(self, ip: str) -> HostInfo | None: ...

    def incident(self) -> IncidentParams: ...

    def row(self, session_id: int) -> Row | None: ...

    def tls_client_profile(self, ja3: str) -> TlsClientProfile | None: ...


class EvidenceEngine(Protocol):
    def decode(self, row: Row, role: Role) -> dict[str, Any]: ...

    def flow(self, row: Row, bucket_ms: int) -> Sequence[FlowSampleData]: ...

    def pcap(self, row: Row) -> bytes: ...

    def enrich(self, ip: str) -> EnrichData: ...

    def protocol_schema(self, protocol: str) -> "ProtocolSchema | None": ...


class World(Protocol):
    @property
    def seed(self) -> str: ...

    @property
    def clock(self) -> "CaptureClock": ...

    @property
    def epoch_ms(self) -> int: ...

    @property
    def data_start_ms(self) -> int: ...

    def capture_now_ms(self) -> int: ...

    def sensors(self) -> Sequence[SensorInfo]: ...

    def sensor(self, sensor_id: str) -> SensorInfo | None: ...

    def visible_until_ms(self, sensor_id: str) -> int: ...

    def outages(self, sensor_id: str) -> Sequence[Outage]: ...

    def rows(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]: ...

    def rows_desc(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]: ...

    def count(self, sensor_id: str, start_ms: int, end_ms: int) -> int: ...

    def row(self, session_id: int) -> Row | None: ...

    def host(self, ip: str) -> HostInfo | None: ...

    def hosts(self) -> Sequence[HostInfo]: ...

    def decoded(self, row: Row, role: Role) -> dict[str, Any]: ...

    def files_for_row(self, row: Row) -> tuple[FileData, ...]: ...

    def file(self, file_id: str) -> FileData | None: ...

    def file_bytes(self, file: FileData) -> bytes: ...

    def flow(self, row: Row, bucket_ms: int) -> Sequence[FlowSampleData]: ...

    def pcap_status(self, row: Row) -> PcapStatus: ...

    def pcap_available(self, row: Row) -> bool: ...

    def pcap(self, row: Row) -> bytes: ...

    def detections_for_row(
        self, row: Row, until_ms: int | None = None
    ) -> Sequence[DetectionData]: ...

    def enrich(self, ip: str) -> EnrichData: ...

    def protocol_schema(self, protocol: str) -> "ProtocolSchema | None": ...

    def detections_until(self, until_ms: int) -> Sequence[DetectionData]: ...

    def detections_after(self, seq: int, until_ms: int) -> Sequence[DetectionData]: ...

    def incident(self) -> IncidentParams: ...

    def truth(self) -> Truth: ...

    def register_import(
        self,
        *,
        import_id: str,
        label: str,
        tz: str,
        sha256: str,
        size: int,
        first_ts_ms: int,
        last_ts_ms: int,
    ) -> SensorInfo: ...

    def clear_imports(self) -> None: ...

    def to_session_row(self, row: Row) -> "SessionRow": ...

    def to_session(self, row: Row, role: Role) -> "Session": ...

    def to_detection(self, detection: DetectionData) -> "Detection": ...

    def to_sensor(self, sensor: SensorInfo) -> "Sensor": ...
