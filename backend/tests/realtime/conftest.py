from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from capture_api.domain.models import Detection, Sensor, SessionRow, Severity
from capture_api.main import create_app
from capture_api.settings import Settings
from capture_api.world import views
from capture_api.world.catalog import BUILTIN_SENSORS, DETECTION_RULES
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import DetectionData, PcapStatus, Row, SensorInfo, World

HQ = "hq-core"
BRANCH = "harbor-branch"
DENIED = "dc-east"
RULES = ("rare_user_agent", "cleartext_credentials", "port_scan")


@dataclass(frozen=True, slots=True)
class Script:
    detections: tuple[DetectionData, ...] = ()
    rows: tuple[Row, ...] = ()


def detection(seq: int, ts_ms: int, *, sensor_id: str = HQ) -> DetectionData:
    rule = RULES[seq % len(RULES)]
    return DetectionData(
        seq=seq,
        id=f"det_{seq}",
        ts_ms=ts_ms,
        rule_id=rule,
        severity=cast(Severity, DETECTION_RULES[rule].severity),
        sensor_id=sensor_id,
        session_id=72_057_594_037_927_936 + seq,
        src_ip="10.20.4.17",
        src_port=49_312 + seq,
        dst_ip="203.0.113.24",
        dst_port=443,
        summary=f"scripted detection {seq}",
    )


def session_row(index: int, start_ms: int, *, sensor_id: str = HQ, protocol: str = "dns") -> Row:
    return Row(
        id=(1 << 56) + index,
        sensor_id=sensor_id,
        start_ms=start_ms,
        end_ms=start_ms + 120,
        protocol=cast(Literal["dns", "tls"], protocol),
        transport="udp" if protocol == "dns" else "tcp",
        src_ip="10.20.4.17",
        src_port=49_000 + index,
        dst_ip="10.20.0.53" if protocol == "dns" else "203.0.113.24",
        dst_port=53 if protocol == "dns" else 443,
        bytes_up=100 + index,
        bytes_down=200 + index,
        packets_up=2,
        packets_down=2,
        risk_score=5,
        risk_reasons=(),
        summary=f"scripted row {index}",
        attrs={"dns.query.name": f"host{index}.example.net"},
    )


def make_script(
    epoch_ms: int, *, history: int = 5, live: int = 5, rows: int = 6, step_ms: int = 10_000
) -> Script:
    detections = [detection(i + 1, epoch_ms - (history - i) * 1_000) for i in range(history)]
    detections += [
        detection(
            history + i + 1,
            epoch_ms + (i + 1) * step_ms,
            sensor_id=BRANCH if i % 2 else HQ,
        )
        for i in range(live)
    ]
    live_rows = [session_row(i, epoch_ms + (i + 1) * 1_000) for i in range(rows)]
    return Script(tuple(detections), tuple(live_rows))


class FakeWorld:
    def __init__(self, clock: CaptureClock, script: Script, *, seed: str = "test") -> None:
        self._clock = clock
        self._script = script
        self._seed = seed
        self._by_sensor: dict[str, list[Row]] = {}
        for item in script.rows:
            self._by_sensor.setdefault(item.sensor_id, []).append(item)

    @property
    def seed(self) -> str:
        return self._seed

    @property
    def clock(self) -> CaptureClock:
        return self._clock

    @property
    def epoch_ms(self) -> int:
        return self._clock.epoch_ms

    @property
    def data_start_ms(self) -> int:
        return self._clock.data_start_ms

    def capture_now_ms(self) -> int:
        return self._clock.now_ms()

    def sensors(self) -> Sequence[SensorInfo]:
        return BUILTIN_SENSORS

    def sensor(self, sensor_id: str) -> SensorInfo | None:
        return next((s for s in BUILTIN_SENSORS if s.id == sensor_id), None)

    def visible_until_ms(self, sensor_id: str) -> int:
        sensor = self.sensor(sensor_id)
        return self.capture_now_ms() - (sensor.lag_s * 1_000 if sensor else 0)

    def outages(self, sensor_id: str) -> Sequence[Any]:
        return ()

    def rows(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]:
        cut = self.visible_until_ms(sensor_id)
        return iter(
            [
                item
                for item in self._by_sensor.get(sensor_id, ())
                if start_ms <= item.start_ms < end_ms and item.start_ms <= cut
            ]
        )

    def rows_desc(self, sensor_id: str, start_ms: int, end_ms: int) -> Iterator[Row]:
        return iter(list(self.rows(sensor_id, start_ms, end_ms))[::-1])

    def count(self, sensor_id: str, start_ms: int, end_ms: int) -> int:
        return len(list(self.rows(sensor_id, start_ms, end_ms)))

    def row(self, session_id: int) -> Row | None:
        return next((r for r in self._script.rows if r.id == session_id), None)

    def host(self, ip: str) -> None:
        return None

    def hosts(self) -> Sequence[Any]:
        return ()

    def decoded(self, row: Row, role: str) -> dict[str, Any]:
        return {}

    def files_for_row(self, row: Row) -> tuple[Any, ...]:
        return ()

    def detections_for_row(self, row: Row, until_ms: int | None = None) -> Sequence[DetectionData]:
        return [d for d in self._script.detections if d.session_id == row.id]

    def pcap_status(self, row: Row) -> PcapStatus:
        return PcapStatus(available=True)

    def pcap_available(self, row: Row) -> bool:
        return True

    def detections_until(self, until_ms: int) -> Sequence[DetectionData]:
        return [d for d in self._script.detections if d.ts_ms <= until_ms]

    def detections_after(self, seq: int, until_ms: int) -> Sequence[DetectionData]:
        return self.detections_until(until_ms)[max(0, seq) :]

    def to_detection(self, data: DetectionData) -> Detection:
        return views.to_detection(cast(views.ViewWorld, self), data)

    def to_session_row(self, item: Row) -> SessionRow:
        return views.to_session_row(cast(views.ViewWorld, self), item)

    def to_sensor(self, sensor: SensorInfo) -> Sensor:
        return views.to_sensor(cast(views.ViewWorld, self), sensor)


@dataclass(frozen=True, slots=True)
class Built:
    client: TestClient
    app: FastAPI
    world: FakeWorld


type ClientFactory = Callable[..., Built]
type AppFactory = Callable[..., FastAPI]


@pytest.fixture
def epoch_ms() -> int:
    return Settings(_env_file=None, seed="test").epoch_ms


@pytest.fixture
def script(epoch_ms: int) -> Script:
    return make_script(epoch_ms)


@pytest.fixture
def make_app(
    fake_time: FakeTimeSource, script: Script, monkeypatch: pytest.MonkeyPatch
) -> AppFactory:
    chosen = [script]

    def build_world(settings: Settings, clock: CaptureClock, engine: Any = None) -> Any:
        return FakeWorld(clock, chosen[0], seed=settings.seed)

    monkeypatch.setattr("capture_api.world.world.build_world", build_world)

    def build(*, world_script: Script | None = None, **overrides: Any) -> FastAPI:
        if world_script is not None:
            chosen[0] = world_script
        settings = Settings(_env_file=None, seed="test", teammate_bot=False, **overrides)
        return create_app(settings, time_source=fake_time)

    return build


@pytest.fixture
def make_realtime(make_app: AppFactory) -> Iterator[ClientFactory]:
    started: list[TestClient] = []

    def build(**overrides: Any) -> Built:
        app = make_app(**overrides)
        client = TestClient(app)
        client.__enter__()
        started.append(client)
        return Built(client, app, app.state.world)

    yield build
    for client in reversed(started):
        client.__exit__(None, None, None)


@pytest.fixture
def realtime(make_realtime: ClientFactory) -> Built:
    return make_realtime()


@pytest.fixture
def client(realtime: Built) -> TestClient:
    return realtime.client


@pytest.fixture
def world(realtime: Built) -> World:
    return cast(World, realtime.world)
