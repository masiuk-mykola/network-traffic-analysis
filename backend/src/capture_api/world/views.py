from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from capture_api.domain.base import from_epoch_ms
from capture_api.domain.models import (
    ByteCount,
    CarvedFile,
    Detection,
    Endpoint,
    Intel,
    Mitre,
    PcapInfo,
    Risk,
    RiskBand,
    RiskReason,
    Sensor,
    SensorRetention,
    Session,
    SessionDetection,
    SessionRow,
    Severity,
)
from capture_api.world.catalog import DETECTION_RULES, RISK_REASONS, risk_band
from capture_api.world.enrich_data import country_for_ip
from capture_api.world.types import (
    DetectionData,
    FileData,
    HostInfo,
    PcapStatus,
    Role,
    Row,
    SensorInfo,
)

INTEL_SOURCE = "OpenIntel (sim)"
LEGACY_LOCAL_FORMAT = "%d/%m/%Y %H:%M:%S"

_ZONES: dict[str, ZoneInfo] = {}


class ViewWorld(Protocol):
    @property
    def seed(self) -> str: ...

    def sensor(self, sensor_id: str) -> SensorInfo | None: ...

    def host(self, ip: str) -> HostInfo | None: ...

    def pcap_status(self, row: Row) -> PcapStatus: ...

    def decoded(self, row: Row, role: Role) -> dict[str, Any]: ...

    def files_for_row(self, row: Row) -> tuple[FileData, ...]: ...

    def detections_for_row(
        self, row: Row, until_ms: int | None = None
    ) -> Sequence[DetectionData]: ...

    def visible_until_ms(self, sensor_id: str) -> int: ...


def zone(tz: str) -> ZoneInfo:
    found = _ZONES.get(tz)
    if found is None:
        found = _ZONES[tz] = ZoneInfo(tz)
    return found


def decoder_string(protocol: str, decoder_version: str) -> str:
    return f"{protocol}/{'1' if decoder_version == 'v1' else '2'}"


def endpoint(world: ViewWorld, ip: str, port: int) -> Endpoint:
    host = world.host(ip)
    return Endpoint(
        ip=ip,
        port=port,
        host=host.hostname if host else None,
        country=(host.country if host else None) or country_for_ip(world.seed, ip),
    )


def risk_of(row: Row) -> Risk:
    reasons = [
        RiskReason(code=definition.code, label=definition.label, mitre=definition.mitre)
        for code in row.risk_reasons
        if (definition := RISK_REASONS.get(code)) is not None
    ]
    return Risk(score=row.risk_score, band=_band(row.risk_score), reasons=reasons)


def to_session_row(world: ViewWorld, row: Row) -> SessionRow:
    sensor = world.sensor(row.sensor_id)
    return SessionRow(
        id=str(row.id),
        sensor_id=row.sensor_id,
        start=from_epoch_ms(row.start_ms),
        end=from_epoch_ms(row.end_ms),
        duration_ms=row.duration_ms,
        protocol=row.protocol,
        transport=row.transport,
        src=endpoint(world, row.src_ip, row.src_port),
        dst=endpoint(world, row.dst_ip, row.dst_port),
        bytes=ByteCount(up=row.bytes_up, down=row.bytes_down),
        packets=ByteCount(up=row.packets_up, down=row.packets_down),
        risk=risk_of(row),
        intel=Intel(score=row.intel_score, source=INTEL_SOURCE) if row.intel_score else None,
        summary=row.summary,
        decoder=decoder_string(row.protocol, sensor.decoder_version if sensor else "v2"),
        files_count=row.files_count,
        pcap_available=world.pcap_status(row).available,
    )


def to_session(world: ViewWorld, row: Row, role: Role) -> Session:
    base = to_session_row(world, row)
    return Session(
        **base.model_dump(by_alias=False),
        decoded=world.decoded(row, role),
        detections=[to_session_detection(d.rule_id) for d in world.detections_for_row(row)],
        files=[to_carved_file(f) for f in world.files_for_row(row)],
        pcap=to_pcap_info(world.pcap_status(row)),
    )


def to_session_detection(rule_id: str) -> SessionDetection:
    rule = DETECTION_RULES[rule_id]
    return SessionDetection(
        rule_id=rule.rule_id,
        rule=rule.name,
        severity=_severity(rule.severity),
        mitre=Mitre(technique_id=rule.technique_id, name=rule.technique_name),
    )


def to_carved_file(file: FileData) -> CarvedFile:
    return CarvedFile(
        id=file.id,
        name=file.name,
        mime=file.mime,
        size=file.size,
        sha256=file.sha256,
        source=file.source,
        purged=file.purged,
    )


def to_pcap_info(status: PcapStatus) -> PcapInfo:
    return PcapInfo(
        available=status.available,
        reason=status.reason,
        expired_at=from_epoch_ms(status.expired_at_ms) if status.expired_at_ms else None,
    )


def to_detection(world: ViewWorld, detection: DetectionData) -> Detection:
    rule = DETECTION_RULES[detection.rule_id]
    return Detection(
        seq=detection.seq,
        id=detection.id,
        ts=from_epoch_ms(detection.ts_ms),
        rule_id=rule.rule_id,
        rule=rule.name,
        severity=_severity(detection.severity),
        mitre=Mitre(technique_id=rule.technique_id, name=rule.technique_name),
        sensor_id=detection.sensor_id,
        session_id=str(detection.session_id),
        src=endpoint(world, detection.src_ip, detection.src_port),
        dst=endpoint(world, detection.dst_ip, detection.dst_port),
        summary=detection.summary,
    )


def to_sensor(world: ViewWorld, sensor: SensorInfo) -> Sensor:
    last_packet_ms = world.visible_until_ms(sensor.id)
    local = datetime.fromtimestamp(last_packet_ms / 1000, UTC).astimezone(zone(sensor.tz))
    return Sensor(
        id=sensor.id,
        name=sensor.name,
        site=sensor.site,
        kind=sensor.kind,
        status=sensor.status,
        decoder_version=sensor.decoder_version,
        tz=sensor.tz,
        retention=SensorRetention(
            metadata_days=sensor.metadata_days,
            pcap_hours=sensor.pcap_hours,
            files_days=sensor.files_days,
        ),
        last_packet_at=from_epoch_ms(last_packet_ms),
        lag_seconds=sensor.lag_s,
        last_packet_local=local.strftime(LEGACY_LOCAL_FORMAT),
    )


def _band(score: int) -> RiskBand:
    return cast(RiskBand, risk_band(score))


def _severity(value: str) -> Severity:
    return cast(Severity, value)
