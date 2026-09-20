from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from capture_api.domain.base import from_epoch_ms
from capture_api.domain.models import (
    GraphEdge,
    GraphNode,
    HistogramBucket,
    PivotBucket,
    PivotSeries,
    SearchGraph,
)
from capture_api.search.compile import Predicate
from capture_api.search.estimate import windows
from capture_api.world.enrich_data import country_for_ip
from capture_api.world.types import Row, World

MIN_BUCKET_S = 60
MAX_BUCKET_S = 86_400
MAX_BUCKETS = 2_000
DEFAULT_GRAPH_NODES = 50


def bucket_count(from_ms: int, to_ms: int, bucket_ms: int) -> int:
    return max(1, -(-(to_ms - from_ms) // bucket_ms))


def _covered_ms(world: World, sensor_id: str, start: int, end: int, window: tuple[int, int]) -> int:
    low = max(start, window[0])
    high = min(end, window[1])
    if high <= low:
        return 0
    covered = high - low
    for outage in world.outages(sensor_id):
        overlap = min(high, outage.end_ms) - max(low, outage.start_ms)
        if overlap > 0:
            covered -= overlap
    return max(0, covered)


@dataclass(slots=True)
class _Bucket:
    by_protocol: dict[str, int] = field(default_factory=dict)
    bytes: int = 0


def histogram(
    world: World,
    sensor_ids: Sequence[str],
    from_ms: int,
    to_ms: int,
    *,
    bucket_s: int,
    predicate: Predicate,
    now_ms: int,
) -> list[HistogramBucket]:
    bucket_ms = bucket_s * 1_000
    count = bucket_count(from_ms, to_ms, bucket_ms)
    resolved = windows(world, sensor_ids, from_ms, to_ms)
    tallies = [_Bucket() for _ in range(count)]
    for sensor_id, start, end in resolved:
        for row in world.rows(sensor_id, start, end):
            if not predicate(row):
                continue
            index = (row.start_ms - from_ms) // bucket_ms
            if not 0 <= index < count:
                continue
            tally = tallies[index]
            tally.by_protocol[row.protocol] = tally.by_protocol.get(row.protocol, 0) + 1
            tally.bytes += row.bytes_up + row.bytes_down

    buckets: list[HistogramBucket] = []
    for index, tally in enumerate(tallies):
        start = from_ms + index * bucket_ms
        end = start + bucket_ms
        covered = sum(
            _covered_ms(world, sensor_id, start, end, (window_start, window_end))
            for sensor_id, window_start, window_end in resolved
        )
        if covered <= 0:
            continue
        coverage = min(1.0, covered / (bucket_ms * max(1, len(resolved))))
        buckets.append(
            HistogramBucket(
                t=from_epoch_ms(start),
                coverage=round(coverage, 4),
                partial=True if start <= now_ms < end else None,
                by_protocol=dict(sorted(tally.by_protocol.items())),
                bytes=tally.bytes,
            )
        )
    return buckets


def pivot_occurrences(
    world: World,
    sensor_ids: Sequence[str],
    from_ms: int,
    to_ms: int,
    *,
    bucket_s: int,
    predicate: Predicate,
) -> list[PivotSeries]:
    bucket_ms = bucket_s * 1_000
    count = bucket_count(from_ms, to_ms, bucket_ms)
    series: list[PivotSeries] = []
    for sensor_id, start, end in windows(world, sensor_ids, from_ms, to_ms):
        counts: dict[int, int] = {}
        for row in world.rows(sensor_id, start, end):
            if not predicate(row):
                continue
            index = (row.start_ms - from_ms) // bucket_ms
            if 0 <= index < count:
                counts[index] = counts.get(index, 0) + 1
        series.append(
            PivotSeries(
                sensor_id=sensor_id,
                buckets=[
                    PivotBucket(t=from_epoch_ms(from_ms + index * bucket_ms), count=counts[index])
                    for index in sorted(counts)
                ],
            )
        )
    return series


@dataclass(slots=True)
class _Node:
    sessions: int = 0
    bytes: int = 0


def _node_kind(world: World, ip: str) -> str:
    host = world.host(ip)
    if host is not None:
        return host.kind
    return "external" if country_for_ip(world.seed, ip) else "internal"


def _node_label(world: World, ip: str) -> str:
    host = world.host(ip)
    return host.hostname if host is not None and host.hostname else ip


def conversation_graph(
    world: World,
    rows: Iterable[Row],
    *,
    limit_nodes: int = DEFAULT_GRAPH_NODES,
    running: bool = False,
) -> SearchGraph:
    nodes: dict[str, _Node] = {}
    edges: dict[tuple[str, str], _Node] = {}
    for row in rows:
        total = row.bytes_up + row.bytes_down
        for ip in (row.src_ip, row.dst_ip):
            node = nodes.setdefault(ip, _Node())
            node.sessions += 1
            node.bytes += total
        pair = (row.src_ip, row.dst_ip) if row.src_ip <= row.dst_ip else (row.dst_ip, row.src_ip)
        edge = edges.setdefault(pair, _Node())
        edge.sessions += 1
        edge.bytes += total

    ranked = sorted(nodes.items(), key=lambda item: (-item[1].bytes, item[0]))[:limit_nodes]
    kept = {ip for ip, _ in ranked}
    return SearchGraph(
        nodes=[
            GraphNode(
                id=ip,
                label=_node_label(world, ip),
                kind="internal" if _node_kind(world, ip) == "internal" else "external",
                sessions=node.sessions,
                bytes=node.bytes,
            )
            for ip, node in ranked
        ],
        edges=[
            GraphEdge(a=a, b=b, sessions=edge.sessions, bytes=edge.bytes)
            for (a, b), edge in sorted(edges.items(), key=lambda item: (-item[1].bytes, item[0]))
            if a in kept and b in kept
        ],
        partial=running or len(kept) < len(nodes),
    )
