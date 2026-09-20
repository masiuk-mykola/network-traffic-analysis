import bisect
import hashlib
import logging
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from capture_api.domain.models import Detection, ProtocolSchema, Sensor, Session, SessionRow
from capture_api.settings import Settings
from capture_api.world import views
from capture_api.world.background import (
    EPHEMERAL_HIGH,
    EPHEMERAL_LOW,
    HOUR_MS,
    BackgroundGenerator,
    RowDraft,
    finalise,
    log_int,
    packets_for,
)
from capture_api.world.catalog import BUILTIN_SENSORS, FIRST_IMPORT_SENSOR_INDEX
from capture_api.world.clock import CaptureClock
from capture_api.world.detections import DetectionLedger
from capture_api.world.filebytes import carve_files, file_bytes, parse_file_id
from capture_api.world.ids import decode_session_id
from capture_api.world.incident import Incident
from capture_api.world.network import Network
from capture_api.world.rng import Stream
from capture_api.world.tls_profiles import TlsClientProfile, profile_index
from capture_api.world.types import (
    DetectionData,
    EnrichData,
    EvidenceEngine,
    FileData,
    FlowSampleData,
    HostInfo,
    IncidentParams,
    Outage,
    PcapStatus,
    Role,
    Row,
    RowTag,
    SensorInfo,
    Truth,
)

log = logging.getLogger(__name__)

PCAP_RETENTION_MS = 48 * HOUR_MS
PCAP_CACHE_SIZE = 64
IMPORT_BYTES_PER_SESSION = 4_096
IMPORT_MAX_SESSIONS = 5_000


@dataclass(frozen=True, slots=True)
class Block:
    rows: tuple[Row, ...]
    starts: tuple[int, ...]

    @classmethod
    def of(cls, rows: Sequence[Row]) -> "Block":
        return cls(tuple(rows), tuple(row.start_ms for row in rows))


EMPTY_BLOCK = Block((), ())


class SimWorld:
    def __init__(self, settings: Settings, clock: CaptureClock) -> None:
        self._seed = settings.seed
        self._clock = clock
        self._epoch_ms = clock.epoch_ms
        self._data_start_ms = clock.data_start_ms
        self._id_base_ms = clock.id_base_ms
        self._first_hour = self._hour_index(self._data_start_ms)
        self._network = Network(self._seed)
        self._incident = Incident(self._seed, self._network, self._epoch_ms)
        self._generator = BackgroundGenerator(
            self._seed,
            self._network,
            BUILTIN_SENSORS,
            id_base_ms=self._id_base_ms,
            epoch_ms=self._epoch_ms,
            scripted=self._incident,
        )
        self._sensors: dict[str, SensorInfo] = {s.id: s for s in BUILTIN_SENSORS}
        self._by_index: dict[int, SensorInfo] = {s.index: s for s in BUILTIN_SENSORS}
        self._imports: dict[str, tuple[SensorInfo, Block, int]] = {}
        self._import_by_sensor: dict[str, str] = {}
        self._blocks: dict[tuple[str, int], Block] = {}
        self._ledger = DetectionLedger(
            self._seed,
            BUILTIN_SENSORS,
            lambda sensor_id, hour: self._block(sensor_id, hour).rows,
            hour_base_ms=self._id_base_ms,
            first_hour=self._first_hour,
        )
        self._profiles: Mapping[str, TlsClientProfile] = profile_index(
            (self._incident.params.c2_client_profile,)
        )
        self._engine: EvidenceEngine | None = None
        self._pcaps: dict[int, bytes] = {}
        self._truth: Truth | None = None

    def attach_engine(self, engine: EvidenceEngine) -> None:
        self._engine = engine

    @property
    def decode_context(self) -> "DecodeView":
        return DecodeView(self)

    @property
    def engine(self) -> EvidenceEngine:
        if self._engine is None:  # pragma: no cover - build_world always attaches one
            raise RuntimeError("the evidence engine has not been attached yet")
        return self._engine

    @property
    def seed(self) -> str:
        return self._seed

    @property
    def clock(self) -> CaptureClock:
        return self._clock

    @property
    def epoch_ms(self) -> int:
        return self._epoch_ms

    @property
    def data_start_ms(self) -> int:
        return self._data_start_ms

    def capture_now_ms(self) -> int:
        return self._clock.now_ms()

    def sensors(self) -> Sequence[SensorInfo]:
        ready = [sensor for sensor, _, _ in self._imports.values()]
        return sorted([*BUILTIN_SENSORS, *ready], key=lambda s: s.index)

    def sensor(self, sensor_id: str) -> SensorInfo | None:
        return self._sensors.get(sensor_id)

    def visible_until_ms(self, sensor_id: str) -> int:
        sensor = self._sensors.get(sensor_id)
        if sensor is None:
            return self.capture_now_ms()
        if sensor.kind == "import":
            import_id = self._import_by_sensor.get(sensor_id, "")
            return self._imports[import_id][2]
        return self.capture_now_ms() - sensor.lag_s * 1000

    def outages(self, sensor_id: str) -> Sequence[Outage]:
        return [o for o in self._incident.outages() if o.sensor_id == sensor_id]

    def rows(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]:
        for block, low, high in self._slices(sensor_id, start_ms, end_ms):
            yield from block.rows[low:high]

    def rows_desc(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]:
        for block, low, high in reversed(list(self._slices(sensor_id, start_ms, end_ms))):
            yield from reversed(block.rows[low:high])

    def count(self, sensor_id: str, start_ms: int, end_ms: int) -> int:
        return sum(high - low for _, low, high in self._slices(sensor_id, start_ms, end_ms))

    def row(self, session_id: int) -> Row | None:
        row = self.raw_row(session_id)
        if row is None or row.start_ms > self.visible_until_ms(row.sensor_id):
            return None
        return row

    def raw_row(self, session_id: int) -> Row | None:
        sensor_index, minute, _ordinal = decode_session_id(session_id)
        sensor = self._by_index.get(sensor_index)
        if sensor is None:
            return None
        block = self._block(sensor.id, minute // 60)
        return next((row for row in block.rows if row.id == session_id), None)

    def host(self, ip: str) -> HostInfo | None:
        return self._network.host(ip)

    def hosts(self) -> Sequence[HostInfo]:
        return self._network.hosts()

    @property
    def network(self) -> Network:
        return self._network

    def tls_client_profile(self, ja3: str) -> TlsClientProfile | None:
        return self._profiles.get(ja3)

    def decoded(self, row: Row, role: Role) -> dict[str, Any]:
        return self.engine.decode(row, role)

    def files_for_row(self, row: Row) -> tuple[FileData, ...]:
        return carve_files(self._seed, row)

    def file(self, file_id: str) -> FileData | None:
        parsed = parse_file_id(file_id)
        if parsed is None:
            return None
        session_id, ordinal = parsed
        row = self.row(session_id)
        if row is None:
            return None
        files = self.files_for_row(row)
        return files[ordinal] if ordinal < len(files) else None

    def file_bytes(self, file: FileData) -> bytes:
        return file_bytes(self._seed, file.id, file.mime, file.size)

    def flow(self, row: Row, bucket_ms: int) -> Sequence[FlowSampleData]:
        return self.engine.flow(row, bucket_ms)

    def pcap_status(self, row: Row) -> PcapStatus:
        sensor = self._sensors.get(row.sensor_id)
        if sensor is not None and sensor.kind == "import":
            return PcapStatus(available=False, reason="not_captured")
        if row.start_ms >= self._epoch_ms - PCAP_RETENTION_MS:
            return PcapStatus(available=True)
        return PcapStatus(
            available=False,
            reason="expired",
            expired_at_ms=row.start_ms + PCAP_RETENTION_MS,
        )

    def pcap_available(self, row: Row) -> bool:
        return self.pcap_status(row).available

    def pcap(self, row: Row) -> bytes:
        cached = self._pcaps.get(row.id)
        if cached is None:
            cached = self.engine.pcap(row)
            if len(self._pcaps) >= PCAP_CACHE_SIZE:
                self._pcaps.clear()
            self._pcaps[row.id] = cached
        return cached

    def enrich(self, ip: str) -> EnrichData:
        return self.engine.enrich(ip)

    def protocol_schema(self, protocol: str) -> ProtocolSchema | None:
        return self.engine.protocol_schema(protocol)

    def detections_until(self, until_ms: int) -> Sequence[DetectionData]:
        return self._ledger.until(until_ms)

    def detections_after(self, seq: int, until_ms: int) -> Sequence[DetectionData]:
        return self._ledger.after(seq, until_ms)

    def detections_for_row(self, row: Row, until_ms: int | None = None) -> Sequence[DetectionData]:
        cut = self.capture_now_ms() if until_ms is None else until_ms
        return self._ledger.for_session(row.id, cut)

    def incident(self) -> IncidentParams:
        return self._incident.params

    def truth(self) -> Truth:
        if self._truth is None:
            self._truth = self._build_truth()
        return self._truth

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
    ) -> SensorInfo:
        existing = self._imports.get(import_id)
        if existing is not None:
            return existing[0]
        index = FIRST_IMPORT_SENSOR_INDEX + len(self._imports)
        sensor = SensorInfo(
            id=f"imp-{index - FIRST_IMPORT_SENSOR_INDEX + 1}",
            index=index,
            name=label,
            site="Imported capture",
            kind="import",
            tz=tz,
            decoder_version="v2",
            status="online",
            lag_s=0,
            pcap_hours=0,
            import_id=import_id,
        )
        first, last = self._clamp_import_window(first_ts_ms, last_ts_ms)
        block = Block.of(self._synthesise_import(sensor, sha256, size, first, last))
        self._imports[import_id] = (sensor, block, last)
        self._import_by_sensor[sensor.id] = import_id
        self._sensors[sensor.id] = sensor
        self._by_index[sensor.index] = sensor
        return sensor

    def clear_imports(self) -> None:
        for sensor_id in list(self._import_by_sensor):
            sensor = self._sensors.pop(sensor_id, None)
            if sensor is not None:
                self._by_index.pop(sensor.index, None)
        self._imports.clear()
        self._import_by_sensor.clear()

    def to_session_row(self, row: Row) -> SessionRow:
        return views.to_session_row(self, row)

    def to_session(self, row: Row, role: Role) -> Session:
        return views.to_session(self, row, role)

    def to_detection(self, detection: DetectionData) -> Detection:
        return views.to_detection(self, detection)

    def to_sensor(self, sensor: SensorInfo) -> Sensor:
        return views.to_sensor(self, sensor)

    def _hour_index(self, ts_ms: int) -> int:
        return (ts_ms - self._id_base_ms) // HOUR_MS

    def _block(self, sensor_id: str, hour: int) -> Block:
        import_id = self._import_by_sensor.get(sensor_id)
        if import_id is not None:
            block = self._imports[import_id][1]
            low = bisect.bisect_left(block.starts, self._id_base_ms + hour * HOUR_MS)
            high = bisect.bisect_left(block.starts, self._id_base_ms + (hour + 1) * HOUR_MS)
            return Block.of(block.rows[low:high])
        if hour < self._first_hour:
            return EMPTY_BLOCK
        key = (sensor_id, hour)
        cached = self._blocks.get(key)
        if cached is None:
            cached = self._blocks[key] = Block.of(self._generator.block(sensor_id, hour))
        return cached

    def _slices(
        self, sensor_id: str, start_ms: int, end_ms: int
    ) -> Iterator[tuple[Block, int, int]]:
        if sensor_id not in self._sensors:
            return
        cut = min(end_ms, self.visible_until_ms(sensor_id) + 1)
        low_ms = max(start_ms, self._data_start_ms)
        if cut <= low_ms:
            return
        for hour in range(self._hour_index(low_ms), self._hour_index(cut - 1) + 1):
            block = self._block(sensor_id, hour)
            if not block.rows:
                continue
            low = bisect.bisect_left(block.starts, start_ms)
            high = bisect.bisect_left(block.starts, cut)
            if high > low:
                yield block, low, high

    def _tagged(self, sensor_id: str, ts_ms: int, tag: RowTag) -> list[Row]:
        block = self._block(sensor_id, self._hour_index(ts_ms))
        return [row for row in block.rows if row.tag == tag]

    def _beacon_row(self, ts_ms: int) -> Row | None:
        rows = self._tagged("harbor-branch", ts_ms, "incident.beacon")
        return next((row for row in rows if row.start_ms == ts_ms), None)

    def _build_truth(self) -> Truth:
        params = self._incident.params
        email = self._tagged("hq-core", params.email_ms, "incident.email")[0]
        contacts = sorted(
            self._tagged("harbor-branch", params.first_contact_ms, "incident.first_contact"),
            key=lambda row: row.start_ms,
        )
        schedule = self._incident.beacons(self._epoch_ms)
        twelfth = self._beacon_row(schedule.times[11])
        retained = self._first_retained_beacon(schedule.times)
        exfil_bytes, exfil_sessions, exfil_start, exfil_end = self._incident.exfil_totals()
        attachment = carve_files(self._seed, email)[0]
        return Truth(
            seed=self._seed,
            patient_zero_ip=params.patient_zero_ip,
            patient_zero_host=params.patient_zero_host,
            patient_zero_user=params.patient_zero_user,
            first_c2_session_id=contacts[0].id,
            first_c2_start_ms=contacts[0].start_ms,
            c2_domain=params.c2_domain,
            c2_ip=params.c2_ip,
            c2_sni=params.c2_sni,
            c2_ja3=params.c2_client_profile.ja3,
            lookalike_domain=params.lookalike_domain,
            attachment_name=params.attachment_name,
            attachment_sha256=attachment.sha256,
            email_session_id=email.id,
            smb_tree="\\\\FS01\\finance$",
            smb_file_count=self._smb_file_count(),
            denied_share="\\\\FS01\\hr$",
            exfil_channel=params.exfil_channel,
            exfil_start_ms=exfil_start,
            exfil_end_ms=exfil_end,
            exfil_bytes_up=exfil_bytes,
            exfil_session_count=exfil_sessions,
            q6_session_id=retained.id if retained else 0,
            q6_pcap_sha256=hashlib.sha256(self.pcap(retained)).hexdigest() if retained else "",
            twelfth_beacon_session_id=twelfth.id if twelfth else 0,
            capture_gap_start_ms=params.capture_gap_start_ms,
            capture_gap_end_ms=params.capture_gap_end_ms,
        )

    def _first_retained_beacon(self, times: Sequence[int]) -> Row | None:
        cut = self._epoch_ms - PCAP_RETENTION_MS
        gap = self._incident.outages()[0]
        for ts in times:
            if ts < cut or gap.start_ms <= ts < gap.end_ms:
                continue
            row = self._beacon_row(ts)
            if row is not None:
                return row
        return None

    def _smb_file_count(self) -> int:
        params = self._incident.params
        first = self._hour_index(params.smb_start_ms)
        last = self._hour_index(params.smb_start_ms + 21 * 60_000)
        return sum(
            1
            for hour in range(first, last + 1)
            for row in self._block("dc-east", hour).rows
            if row.tag == "incident.smb"
        )

    def _clamp_import_window(self, first_ts_ms: int, last_ts_ms: int) -> tuple[int, int]:
        first = max(self._id_base_ms, min(first_ts_ms, last_ts_ms))
        last = max(first, min(max(first_ts_ms, last_ts_ms), self._epoch_ms + 30 * 24 * HOUR_MS))
        return first, last

    def _synthesise_import(
        self, sensor: SensorInfo, sha256: str, size: int, first_ms: int, last_ms: int
    ) -> tuple[Row, ...]:
        count = max(1, min(IMPORT_MAX_SESSIONS, size // IMPORT_BYTES_PER_SESSION))
        stream = Stream(self._seed, "import", sha256)
        span = max(1, last_ms - first_ms)
        services = self._network.services()
        sources = self._network.hq_workstations
        drafts: list[RowDraft] = []
        for index in range(count):
            start = first_ms + index * span // count
            source = stream.choice(sources)
            service = stream.choice(services)
            drafts.append(_import_draft(stream, start, source.ip, service.domain, service.ips[0]))
        return finalise(self._seed, drafts, sensor, self._id_base_ms)


def _import_draft(stream: Stream, start: int, src_ip: str, domain: str, dst_ip: str) -> RowDraft:
    up = log_int(stream, 300, 40_000)
    down = log_int(stream, 500, 300_000)
    return RowDraft(
        start_ms=start,
        end_ms=start + log_int(stream, 30, 20_000),
        protocol="tls",
        transport="tcp",
        src_ip=src_ip,
        src_port=stream.randint(EPHEMERAL_LOW, EPHEMERAL_HIGH),
        dst_ip=dst_ip,
        dst_port=443,
        bytes_up=up,
        bytes_down=down,
        packets_up=packets_for(up, overhead=6),
        packets_down=packets_for(down, overhead=6),
        risk_score=stream.randbelow(24),
        summary=f"TLS1.3 {domain}",
        attrs={
            "tls.sni": domain,
            "tls.ja3": "",
            "tls.version": "TLS1.3",
            "tls.cert_cn": domain,
            "tls.cert_issuer": "Example Trust Services CA",
        },
    )


class DecodeView:
    __slots__ = ("_world",)

    def __init__(self, world: SimWorld) -> None:
        self._world = world

    @property
    def seed(self) -> str:
        return self._world.seed

    @property
    def epoch_ms(self) -> int:
        return self._world.epoch_ms

    def sensor(self, sensor_id: str) -> SensorInfo | None:
        return self._world.sensor(sensor_id)

    def host(self, ip: str) -> HostInfo | None:
        return self._world.host(ip)

    def incident(self) -> IncidentParams:
        return self._world.incident()

    def row(self, session_id: int) -> Row | None:
        return self._world.raw_row(session_id)

    def tls_client_profile(self, ja3: str) -> TlsClientProfile | None:
        return self._world.tls_client_profile(ja3)


class PendingEngine:
    def decode(self, row: Row, role: Role) -> dict[str, Any]:  # noqa: ARG002
        return {}

    def flow(self, row: Row, bucket_ms: int) -> Sequence[FlowSampleData]:  # noqa: ARG002
        return ()

    def pcap(self, row: Row) -> bytes:  # noqa: ARG002
        return b""

    def enrich(self, ip: str) -> EnrichData:
        return EnrichData(ip=ip, reputation="unknown")

    def protocol_schema(self, protocol: str) -> ProtocolSchema | None:  # noqa: ARG002
        return None


def build_world(
    settings: Settings, clock: CaptureClock, engine: EvidenceEngine | None = None
) -> SimWorld:
    world = SimWorld(settings, clock)
    world.attach_engine(engine if engine is not None else _evidence_engine(world))
    return world


def _evidence_engine(world: SimWorld) -> EvidenceEngine:
    try:
        from capture_api.world.decode import build_evidence_engine  # noqa: PLC0415
    except ModuleNotFoundError:
        log.warning("capture_api.world.decode is missing; serving empty evidence")
        return PendingEngine()
    return build_evidence_engine(world.decode_context)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.world = build_world(app.state.settings, app.state.clock)
    try:
        yield
    finally:
        app.state.world = None
