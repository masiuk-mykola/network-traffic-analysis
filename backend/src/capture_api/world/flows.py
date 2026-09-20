from collections.abc import Sequence

from capture_api.world.rng import Stream
from capture_api.world.types import FlowSampleData, Row

MAX_SAMPLES = 240
"""Upper bound on emitted buckets, whatever the bucket size."""

type Profile = str


def _profile(row: Row) -> Profile:
    if row.tag == "incident.beacon":
        return "burst"
    if row.tag == "incident.exfil" or row.bytes_up >= 1_000_000:
        return "upload"
    if row.tag == "herring.backup" or row.bytes_down >= 4_000_000:
        return "bulk"
    if row.duration_ms >= 60_000:
        return "idle"
    if row.protocol in {"dns", "ntp"} or row.duration_ms < 2_000:
        return "short"
    return "short"


def _spread(total: int, weights: Sequence[float]) -> list[int]:
    if not weights:
        return []
    if total <= 0:
        return [0] * len(weights)
    scale = sum(weights) or 1.0
    exact = [total * weight / scale for weight in weights]
    out = [int(value) for value in exact]
    remainder = total - sum(out)
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - out[i]), i))
    for step in range(remainder):
        out[order[step % len(order)]] += 1
    return out


def _cluster_indices(stream: Stream, buckets: int, count: int) -> list[int]:
    clusters = max(1, min(6, count // 3 or 1))
    per_cluster = max(1, count // clusters)
    chosen: set[int] = set()
    span = max(1, buckets // clusters)
    for cluster in range(clusters):
        base = cluster * span + stream.randbelow(max(1, span - per_cluster + 1))
        for offset in range(per_cluster):
            index = base + offset
            if index < buckets:
                chosen.add(index)
    return sorted(chosen) or [0]


def _indices(stream: Stream, profile: Profile, buckets: int, count: int) -> list[int]:
    count = max(1, min(count, buckets))
    if profile == "burst":
        return list(range(count))
    if profile in {"upload", "bulk"}:
        step = buckets / count
        return sorted({min(buckets - 1, int(index * step)) for index in range(count)})
    if profile == "idle":
        return _cluster_indices(stream, buckets, count)
    head = max(1, min(buckets, count * 2))
    return sorted(stream.sample(range(head), min(count, head)))


def _target_count(stream: Stream, profile: Profile, buckets: int, packets: int) -> int:
    ranges = {
        "burst": (2, 6),
        "short": (1, 8),
        "idle": (6, 30),
        "upload": (24, MAX_SAMPLES),
        "bulk": (24, MAX_SAMPLES),
    }
    low, high = ranges.get(profile, (1, 8))
    wanted = stream.randint(low, min(high, max(low, MAX_SAMPLES)))
    return max(1, min(wanted, buckets, max(1, packets)))


def _weights(stream: Stream, profile: Profile, count: int) -> tuple[list[float], list[float]]:
    if profile == "burst":
        up = [1.0 / (index + 1) for index in range(count)]
        return up, list(up)
    if profile == "upload":
        up = [stream.uniform(0.8, 1.2) for _ in range(count)]
        down = [1.0 + (3.0 if index in {0, count - 1} else 0.0) for index in range(count)]
        return up, down
    if profile == "bulk":
        down = [stream.uniform(0.8, 1.2) for _ in range(count)]
        up = [1.0 + (2.0 if index == 0 else 0.0) for index in range(count)]
        return up, down
    weights = [stream.uniform(0.5, 1.5) for _ in range(count)]
    return weights, list(weights)


def flow_samples(row: Row, bucket_ms: int, *, seed: str) -> tuple[FlowSampleData, ...]:
    if bucket_ms <= 0:
        raise ValueError("bucket_ms must be positive")
    stream = Stream(seed, "flow", row.id, bucket_ms)
    buckets = row.duration_ms // bucket_ms + 1
    profile = _profile(row)
    packets = row.packets_up + row.packets_down
    count = _target_count(stream, profile, buckets, packets)
    indices = _indices(stream, profile, buckets, count)
    weight_up, weight_down = _weights(stream, profile, len(indices))
    bytes_up = _spread(row.bytes_up, weight_up)
    bytes_down = _spread(row.bytes_down, weight_down)
    packets_up = _spread(row.packets_up, weight_up)
    packets_down = _spread(row.packets_down, weight_down)
    base = row.start_ms - row.start_ms % bucket_ms
    samples = [
        FlowSampleData(
            t_ms=base + index * bucket_ms,
            bytes_up=bytes_up[slot],
            bytes_down=bytes_down[slot],
            packets_up=packets_up[slot],
            packets_down=packets_down[slot],
        )
        for slot, index in enumerate(indices)
    ]
    return tuple(
        sample
        for sample in samples
        if sample.bytes_up or sample.bytes_down or sample.packets_up or sample.packets_down
    )
