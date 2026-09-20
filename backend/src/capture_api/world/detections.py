import bisect
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, cast

from capture_api.world.catalog import DETECTION_RULES
from capture_api.world.rng import stable_int
from capture_api.world.types import DetectionData, Row, SensorInfo

HOUR_MS = 3_600_000
MIN_DELAY_MS = 1_000
MAX_DELAY_MS = 30_000

type BlockReader = Callable[[str, int], Sequence[Row]]


def release_ms(seed: str, row: Row, lag_s: int, rule_id: str) -> int:
    span = MAX_DELAY_MS - MIN_DELAY_MS
    delay = MIN_DELAY_MS + stable_int(seed, "detection-delay", row.id, rule_id, bits=32) % span
    return row.start_ms + lag_s * 1000 + delay


def detection_id(session_id: int, rule_id: str) -> str:
    return f"det_{session_id}_{rule_id}"


def summarise(rule_id: str, row: Row) -> str:
    builder = _SUMMARIES.get(rule_id)
    return builder(row) if builder else DETECTION_RULES[rule_id].name


def _text(row: Row, key: str, fallback: str) -> str:
    value = row.attr_str(key)
    return value or fallback


_SUMMARIES: Mapping[str, Callable[[Row], str]] = {
    "periodic_tls_beacon": lambda row: (
        f"Repeating TLS sessions from {row.src_ip} to {_text(row, 'tls.sni', row.dst_ip)}"
    ),
    "lookalike_sender": lambda row: (
        f"Mail from look-alike sender {_text(row, 'smtp.mail_from', row.src_ip)}"
    ),
    "smb_mass_read": lambda row: (
        f"Many files read from {_text(row, 'smb2.tree', 'a network share')} by {row.src_ip}"
    ),
    "port_scan": lambda row: f"Port-scan pattern from {row.src_ip} against {row.dst_ip}",
    "dns_tunnel_suspected": lambda row: (
        f"Unusually long DNS label: {_text(row, 'dns.query.name', row.dst_ip)[:80]}"
    ),
    "cleartext_credentials": lambda row: (
        f"Clear-text credentials to {_text(row, 'http.host', row.dst_ip)}"
    ),
    "rare_user_agent": lambda row: (
        f"Rare user agent {_text(row, 'http.user_agent', 'unknown')} to "
        f"{_text(row, 'http.host', row.dst_ip)}"
    ),
}


class DetectionLedger:
    __slots__ = (
        "_all",
        "_block",
        "_by_session",
        "_first_hour",
        "_hour_base_ms",
        "_next_hour",
        "_seed",
        "_sensors",
        "_timestamps",
    )

    def __init__(
        self,
        seed: str,
        sensors: Sequence[SensorInfo],
        block: BlockReader,
        *,
        hour_base_ms: int,
        first_hour: int,
    ) -> None:
        self._seed = seed
        self._sensors = tuple(sorted(sensors, key=lambda s: s.index))
        self._block = block
        self._hour_base_ms = hour_base_ms
        self._first_hour = first_hour
        self._next_hour = first_hour
        self._all: list[DetectionData] = []
        self._timestamps: list[int] = []
        self._by_session: dict[int, list[DetectionData]] = {}

    def until(self, until_ms: int) -> Sequence[DetectionData]:
        self._ensure(self._hour_of(until_ms))
        return self._all[: bisect.bisect_right(self._timestamps, until_ms)]

    def after(self, seq: int, until_ms: int) -> Sequence[DetectionData]:
        return self.until(until_ms)[max(0, seq) :]

    def for_session(self, session_id: int, until_ms: int) -> Sequence[DetectionData]:
        self._ensure(self._hour_of(until_ms))
        return [d for d in self._by_session.get(session_id, ()) if d.ts_ms <= until_ms]

    def last_seq(self, until_ms: int) -> int:
        released = self.until(until_ms)
        return released[-1].seq if released else 0

    def oldest_seq(self) -> int:
        return self._all[0].seq if self._all else 0

    def _hour_of(self, ts_ms: int) -> int:
        return (ts_ms - self._hour_base_ms) // HOUR_MS

    def _ensure(self, hour: int) -> None:
        while self._next_hour <= hour:
            self._build(self._next_hour)
            self._next_hour += 1

    def _build(self, hour: int) -> None:
        window_start = self._hour_base_ms + hour * HOUR_MS
        window_end = window_start + HOUR_MS
        candidates: list[tuple[int, int, int, str, Row, SensorInfo]] = []
        for sensor in self._sensors:
            for source_hour in (hour - 1, hour):
                if source_hour < self._first_hour:
                    continue
                for row in self._block(sensor.id, source_hour):
                    rules = row.attrs.get("detection.rule")
                    if not isinstance(rules, tuple):
                        continue
                    for rule_id in rules:
                        ts = release_ms(self._seed, row, sensor.lag_s, rule_id)
                        if window_start <= ts < window_end:
                            candidates.append((ts, sensor.index, row.id, rule_id, row, sensor))
        candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        seq = len(self._all)
        for ts, _index, session_id, rule_id, row, sensor in candidates:
            seq += 1
            detection = DetectionData(
                seq=seq,
                id=detection_id(session_id, rule_id),
                ts_ms=ts,
                rule_id=rule_id,
                severity=_severity(rule_id),
                sensor_id=sensor.id,
                session_id=session_id,
                src_ip=row.src_ip,
                src_port=row.src_port,
                dst_ip=row.dst_ip,
                dst_port=row.dst_port,
                summary=summarise(rule_id, row),
            )
            self._all.append(detection)
            self._timestamps.append(ts)
            self._by_session.setdefault(session_id, []).append(detection)


def _severity(rule_id: str) -> Literal["low", "medium", "high"]:
    rule = DETECTION_RULES.get(rule_id)
    return cast(Literal["low", "medium", "high"], rule.severity) if rule else "low"
