import bisect
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from capture_api.settings import Settings
from capture_api.world.catalog import BUILTIN_SENSOR_IDS
from capture_api.world.clock import CaptureClock, FakeTimeSource
from capture_api.world.types import FileSpec, Row
from capture_api.world.world import SimWorld, build_world

SEED = "test"
"""Must match the root ``settings`` fixture, or the ids below address another world."""

PCAP_RETENTION_MS = 48 * 3_600_000
RELATED_WINDOW_MS = 6 * 3_600_000
ADMIN_HEADERS = {"X-Admin-Token": "lf-dev-admin"}


@lru_cache(maxsize=1)
def scan_world() -> SimWorld:
    settings = Settings(_env_file=None, seed=SEED, teammate_bot=False)
    return build_world(settings, CaptureClock(settings.epoch, FakeTimeSource()))


@lru_cache(maxsize=2)
def world_ahead(seconds: int) -> SimWorld:
    settings = Settings(_env_file=None, seed=SEED, teammate_bot=False)
    time_source = FakeTimeSource()
    clock = CaptureClock(settings.epoch, time_source)
    time_source.advance(seconds)
    return build_world(settings, clock)


@dataclass(frozen=True)
class Carved:
    row: Row
    spec: FileSpec
    ordinal: int

    @property
    def session_id(self) -> str:
        return str(self.row.id)

    @property
    def file_id(self) -> str:
        return f"f{self.row.id}-{self.ordinal}"


@dataclass(frozen=True)
class Catalog:
    trap: Carved
    purged: Carved
    path_separators: Carved
    non_ascii: Carved
    plain_file: Carved
    smtp_with_recipients: Row
    dc_east: Row
    harbor_with_pcap: Row
    pcap_retained: Row
    pcap_expired: Row
    long_session: Row
    detected: Row
    busy: Row
    busy_related: int


def _carved(row: Row, ordinal: int) -> Carved:
    return Carved(row=row, spec=row.files[ordinal], ordinal=ordinal)


@lru_cache(maxsize=1)
def catalog() -> Catalog:  # noqa: PLR0912 - one pass, many small pickers
    world = scan_world()
    now = world.capture_now_ms()
    retention_cut = world.epoch_ms - PCAP_RETENTION_MS
    found: dict[str, object] = {}
    starts: dict[tuple[str, frozenset[str]], list[int]] = defaultdict(list)
    rows_by_pair: dict[tuple[str, frozenset[str]], list[Row]] = defaultdict(list)

    for sensor_id in BUILTIN_SENSOR_IDS:
        for row in world.rows(sensor_id, world.data_start_ms, now + 1):
            pair = (sensor_id, frozenset((row.src_ip, row.dst_ip)))
            starts[pair].append(row.start_ms)
            rows_by_pair[pair].append(row)
            for ordinal, spec in enumerate(row.files):
                if spec.trap:
                    found.setdefault("trap", _carved(row, ordinal))
                elif spec.purged:
                    found.setdefault("purged", _carved(row, ordinal))
                elif "\\" in spec.name or "/" in spec.name:
                    found.setdefault("path_separators", _carved(row, ordinal))
                elif not spec.name.isascii():
                    found.setdefault("non_ascii", _carved(row, ordinal))
                elif row.start_ms >= retention_cut:
                    found.setdefault("plain_file", _carved(row, ordinal))
            if row.protocol == "smtp" and row.attr("smtp.rcpt_to"):
                found.setdefault("smtp_with_recipients", row)
            if sensor_id == "dc-east":
                found.setdefault("dc_east", row)
            if sensor_id == "harbor-branch" and row.start_ms >= retention_cut:
                found.setdefault("harbor_with_pcap", row)
            if row.start_ms >= retention_cut:
                found.setdefault("pcap_retained", row)
            else:
                found["pcap_expired"] = row
            if row.duration_ms > 600_000:
                found.setdefault("long_session", row)
            if row.attr("detection.rule") and sensor_id == "hq-core":
                found.setdefault("detected", row)

    busy, busy_related = _busiest_pair(starts, rows_by_pair)
    return Catalog(
        trap=_file(found, "trap"),
        purged=_file(found, "purged"),
        path_separators=_file(found, "path_separators"),
        non_ascii=_file(found, "non_ascii"),
        plain_file=_file(found, "plain_file"),
        smtp_with_recipients=_row(found, "smtp_with_recipients"),
        dc_east=_row(found, "dc_east"),
        harbor_with_pcap=_row(found, "harbor_with_pcap"),
        pcap_retained=_row(found, "pcap_retained"),
        pcap_expired=_row(found, "pcap_expired"),
        long_session=_row(found, "long_session"),
        detected=_row(found, "detected"),
        busy=busy,
        busy_related=busy_related,
    )


def _busiest_pair(
    starts: dict[tuple[str, frozenset[str]], list[int]],
    rows_by_pair: dict[tuple[str, frozenset[str]], list[Row]],
) -> tuple[Row, int]:
    for pair, values in starts.items():
        if len(values) <= 101:
            continue
        values.sort()
        for index, start in enumerate(values):
            low = bisect.bisect_left(values, start - RELATED_WINDOW_MS)
            high = bisect.bisect_right(values, start + RELATED_WINDOW_MS)
            if high - low > 101:
                return rows_by_pair[pair][index], high - low - 1
    raise AssertionError("no address pair is busy enough to paginate /related")


def _row(found: Mapping[str, object], key: str) -> Row:
    value = found.get(key)
    assert isinstance(value, Row), f"the world for seed '{SEED}' has no {key} row"
    return value


def _file(found: Mapping[str, object], key: str) -> Carved:
    value = found.get(key)
    assert isinstance(value, Carved), f"the world for seed '{SEED}' has no {key} file"
    return value


@pytest.fixture(scope="session")
def world() -> SimWorld:
    return scan_world()


@pytest.fixture(scope="session")
def rows() -> Catalog:
    return catalog()


def set_chaos(client: TestClient, profile: str) -> None:
    response = client.put("/v1/__admin/chaos", json={"profile": profile}, headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text


def parse_content_disposition(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    match = re.search(r'filename="([^"]*)"', value)
    if match:
        parsed["filename"] = match.group(1)
    match = re.search(r"filename\*=UTF-8''([^;]+)", value)
    if match:
        parsed["filename*"] = unquote(match.group(1), encoding="utf-8")
    return parsed
