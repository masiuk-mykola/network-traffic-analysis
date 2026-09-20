import argparse
import hashlib
import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from capture_api.cli import command
from capture_api.settings import Settings
from capture_api.world.clock import CaptureClock, SystemTimeSource

PCAP_HEADER_BYTES = 24
DEFAULT_SIZE_MB = 60
NOT_A_CAPTURE_SIZE = 4096
EXIT_MISSING_WORLD = 4
WINDOW_HOURS = 24


class WorldUnavailableError(RuntimeError): ...


def build_world_or_explain(seed: str) -> Any:
    try:
        module = importlib.import_module("capture_api.world.world")
    except ModuleNotFoundError as exc:  # pragma: no cover - only before the world lands
        raise WorldUnavailableError(
            "capture_api.world.world is missing: this command needs the generated world."
        ) from exc
    builder = getattr(module, "build_world", None)
    if builder is None:  # pragma: no cover - only before the world lands
        raise WorldUnavailableError("capture_api.world.world has no build_world(settings, clock)")
    settings = Settings(_env_file=None, seed=seed)
    clock = CaptureClock(settings.epoch, SystemTimeSource())
    return builder(settings, clock)


def _captures(world: Any) -> Iterator[bytes]:
    end = world.capture_now_ms()
    start = max(world.data_start_ms, end - WINDOW_HOURS * 3_600_000)
    for sensor in world.sensors():
        for row in world.rows_desc(sensor.id, start, end):
            try:
                yield world.pcap(row)
            except Exception as exc:  # pragma: no cover - a writer that cannot render a row
                message = f"the PCAP writer failed on session {row.id}: {exc}"
                raise WorldUnavailableError(message) from exc


def write_lab_capture(world: Any, out: Path, size_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    written = 0
    with out.open("wb") as handle:
        for index, capture in enumerate(_captures(world)):
            if len(capture) <= PCAP_HEADER_BYTES:
                continue
            chunk = capture if index == 0 else capture[PCAP_HEADER_BYTES:]
            handle.write(chunk)
            digest.update(chunk)
            written += len(chunk)
            if written >= size_bytes:
                break
    if written == 0:
        raise WorldUnavailableError("the world produced no sessions to build a sample from")
    return written, digest.hexdigest()


def write_not_a_capture(out: Path) -> tuple[int, str]:
    banner = (
        b"This is not a packet capture. POST /v1/imports must answer 415 not_a_capture for it.\n"
    )
    payload = banner + b"." * (NOT_A_CAPTURE_SIZE - len(banner))
    out.write_bytes(payload)
    return len(payload), hashlib.sha256(payload).hexdigest()


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default="samples", help="output directory (default: samples/)")
    parser.add_argument("--seed", default="samples", help="world seed to build the sample from")
    parser.add_argument(
        "--size-mb", type=int, default=DEFAULT_SIZE_MB, help="approximate size of lab-capture.pcap"
    )


@command("make-samples", help="Write the sample capture uploads.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        world = build_world_or_explain(args.seed)
        size, sha = write_lab_capture(world, out / "lab-capture.pcap", args.size_mb * 1024 * 1024)
    except WorldUnavailableError as exc:
        print(f"cannot build the sample capture: {exc}")
        return EXIT_MISSING_WORLD
    print(f"wrote {out / 'lab-capture.pcap'} ({size / 1_048_576:.1f} MB, sha256 {sha})")
    size, sha = write_not_a_capture(out / "not-a-capture.pcap")
    print(f"wrote {out / 'not-a-capture.pcap'} ({size} bytes, sha256 {sha})")
    return 0
