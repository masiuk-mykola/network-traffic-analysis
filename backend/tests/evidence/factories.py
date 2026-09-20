from dataclasses import dataclass, field, replace
from typing import Any

from capture_api.world.catalog import BUILTIN_SENSORS
from capture_api.world.rng import Stream
from capture_api.world.ssh_profiles import SSH_CLIENT_PROFILES
from capture_api.world.tls_profiles import (
    BACKGROUND_CLIENT_PROFILES,
    VENDOR_UPDATER_PROFILE,
    TlsClientProfile,
    derive_c2_client_profile,
)
from capture_api.world.types import (
    AttrValue,
    FileSpec,
    HostInfo,
    IncidentParams,
    Row,
    RowTag,
    SensorInfo,
)

SEED = "test"
EPOCH_MS = 1_761_566_400_000
"""2025-10-27T12:00:00Z."""

C2_PROFILE: TlsClientProfile = derive_c2_client_profile(Stream(SEED, "incident"))

HOSTS: dict[str, HostInfo] = {
    "10.20.4.17": HostInfo(
        ip="10.20.4.17",
        hostname="ws-hq-017.quillmere.example",
        kind="internal",
        role="workstation",
        user="mira.balogun",
        sensor_id="hq-core",
    ),
    "10.20.40.9": HostInfo(
        ip="10.20.40.9",
        hostname="ws-hb-042.quillmere.example",
        kind="internal",
        role="workstation",
        user="tomas.ferreira",
        sensor_id="harbor-branch",
    ),
    "10.20.1.10": HostInfo(
        ip="10.20.1.10",
        hostname="fs01.quillmere.example",
        kind="internal",
        role="server",
        sensor_id="dc-east",
    ),
    "203.0.113.24": HostInfo(
        ip="203.0.113.24",
        hostname="telemetry.cdn-metrics.test",
        kind="external",
        role="peer",
        country="NL",
    ),
    "192.0.2.10": HostInfo(
        ip="192.0.2.10",
        hostname="static.example.com",
        kind="external",
        role="service",
        country="PT",
    ),
}

INCIDENT = IncidentParams(
    seed=SEED,
    patient_zero_ip="10.20.40.9",
    patient_zero_host="ws-hb-042.quillmere.example",
    patient_zero_user="tomas.ferreira",
    lookalike_domain="quillmere-frieght.example",
    lookalike_sender_ip="198.51.100.31",
    c2_domain="cdn-metrics.test",
    c2_ip="203.0.113.24",
    c2_upload_ip="203.0.113.25",
    c2_client_profile=C2_PROFILE,
    cert_cn="a1b2.invalid",
    beacon_interval_s=300,
    beacon_jitter=0.1,
    email_ms=EPOCH_MS - 61 * 3_600_000,
    first_contact_ms=EPOCH_MS - 60 * 3_600_000,
    beacon_start_ms=EPOCH_MS - 59 * 3_600_000,
    smb_start_ms=EPOCH_MS - 40 * 3_600_000,
    exfil_start_ms=EPOCH_MS - 38 * 3_600_000,
    exfil_end_ms=EPOCH_MS - 36 * 3_600_000,
    smb_file_count=1_284,
    exfil_channel="https_upload",
    exfil_sessions=360,
    exfil_target_bytes=1_900_000_000,
    http_put_ip="198.51.100.77",
    attachment_name="Frachtraten-Q3-Übersicht.xlsm",
    capture_gap_start_ms=EPOCH_MS - 20 * 3_600_000,
    capture_gap_end_ms=EPOCH_MS - 20 * 3_600_000 + 900_000,
)


@dataclass
class FakeContext:
    seed: str = SEED
    epoch_ms: int = EPOCH_MS
    rows_by_id: dict[int, Row] = field(default_factory=dict)
    sensors_by_id: dict[str, SensorInfo] = field(
        default_factory=lambda: {sensor.id: sensor for sensor in BUILTIN_SENSORS}
    )
    hosts_by_ip: dict[str, HostInfo] = field(default_factory=lambda: dict(HOSTS))

    def sensor(self, sensor_id: str) -> SensorInfo | None:
        return self.sensors_by_id.get(sensor_id)

    def host(self, ip: str) -> HostInfo | None:
        return self.hosts_by_ip.get(ip)

    def incident(self) -> IncidentParams:
        return INCIDENT

    def row(self, session_id: int) -> Row | None:
        return self.rows_by_id.get(session_id)

    def tls_client_profile(self, ja3: str) -> TlsClientProfile | None:
        known = (*BACKGROUND_CLIENT_PROFILES, VENDOR_UPDATER_PROFILE, C2_PROFILE)
        return next((profile for profile in known if profile.ja3 == ja3), None)


_BASE_ATTRS: dict[str, dict[str, AttrValue]] = {
    "dns": {
        "dns.query.name": "telemetry.cdn-metrics.test",
        "dns.query.type": "A",
        "dns.rcode": "NOERROR",
        "dns.answer": ("203.0.113.24",),
        "dns.ttl": 60,
    },
    "http": {
        "http.host": "198.51.100.77",
        "http.method": "PUT",
        "http.status": 200,
        "http.path": "/bkt/obj-0004821",
        "http.user_agent": "FreightSync/2.4 (+https://quillmere.example/agent)",
    },
    "tls": {
        "tls.sni": "telemetry.cdn-metrics.test",
        "tls.ja3": C2_PROFILE.ja3,
        "tls.version": "TLS1.2",
        "tls.cert_cn": "a1b2.invalid",
        "tls.cert_issuer": "a1b2.invalid",
    },
    "smtp": {
        "smtp.mail_from": "billing@quillmere-frieght.example",
        "smtp.rcpt_to": ("tomas.ferreira@quillmere.example",),
        "smtp.subject": "Überfällige Rechnung 88213",
    },
    "smb2": {
        "smb2.tree": "\\\\FS01\\finance$",
        "smb2.path": ("\\Invoices\\2026\\INV-000481.pdf",),
        "smb2.status": "STATUS_SUCCESS",
    },
    "ssh": {
        "ssh.hassh": SSH_CLIENT_PROFILES[0].hassh,
        "ssh.server_version": "SSH-2.0-OpenSSH_9.6",
    },
    "ntp": {},
    "tcp": {},
}

_PORTS: dict[str, tuple[int, str]] = {
    "dns": (53, "udp"),
    "http": (80, "tcp"),
    "tls": (443, "tcp"),
    "smtp": (25, "tcp"),
    "smb2": (445, "tcp"),
    "ssh": (22, "tcp"),
    "ntp": (123, "udp"),
    "tcp": (9100, "tcp"),
}


def session_id(sensor_index: int, minute: int, ordinal: int) -> int:
    return (sensor_index << 56) | (minute << 20) | ordinal


def make_row(
    protocol: str = "tls",
    *,
    sensor_id: str = "hq-core",
    row_id: int | None = None,
    src_ip: str = "10.20.4.17",
    dst_ip: str = "203.0.113.24",
    start_ms: int = EPOCH_MS - 3_600_000,
    duration_ms: int = 3_400,
    bytes_up: int = 1_120,
    bytes_down: int = 3_240,
    packets_up: int = 9,
    packets_down: int = 11,
    attrs: dict[str, AttrValue] | None = None,
    files: tuple[FileSpec, ...] = (),
    tag: RowTag | None = None,
    **overrides: Any,
) -> Row:
    port, transport = _PORTS[protocol]
    merged: dict[str, AttrValue] = dict(_BASE_ATTRS[protocol])
    if attrs:
        merged.update(attrs)
    row = Row(
        id=row_id if row_id is not None else session_id(1, 26_402_940, 7),
        sensor_id=sensor_id,
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
        protocol=protocol,  # type: ignore[arg-type]
        transport=transport,  # type: ignore[arg-type]
        src_ip=src_ip,
        src_port=49_312,
        dst_ip=dst_ip,
        dst_port=port,
        bytes_up=bytes_up,
        bytes_down=bytes_down,
        packets_up=packets_up,
        packets_down=packets_down,
        risk_score=12,
        risk_reasons=(),
        summary=f"{protocol} session",
        attrs=merged,
        files=files,
        tag=tag,
    )
    return replace(row, **overrides) if overrides else row
