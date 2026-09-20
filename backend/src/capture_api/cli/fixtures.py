import argparse
import json
from pathlib import Path
from typing import Any

from capture_api.cli import command
from capture_api.cli.samples import (
    EXIT_MISSING_WORLD,
    WorldUnavailableError,
    build_world_or_explain,
)
from capture_api.world.catalog import COLUMN_DEFS, FIELD_DEFS, HARBOR_BRANCH, PROTOCOLS

WINDOW_HOURS = 48
ROW_SAMPLE = 12


def _write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
    return str(path)


def _rows_for(world: Any, sensor_id: str, protocol: str, limit: int) -> list[Any]:
    end = world.capture_now_ms()
    start = max(world.data_start_ms, end - WINDOW_HOURS * 3_600_000)
    found: list[Any] = []
    for row in world.rows_desc(sensor_id, start, end):
        if row.protocol == protocol:
            found.append(row)
            if len(found) >= limit:
                break
    return found


def _single_answer_first(world: Any, rows: list[Any], protocol: str) -> list[Any]:
    if protocol != "dns":
        return rows

    def collapses(row: Any) -> bool:
        payload = world.decoded(row, "analyst").get("dns", {})
        answers = payload.get("answers")
        return isinstance(answers, dict)

    return sorted(rows, key=lambda row: not collapses(row))


def export(world: Any, out: Path) -> dict[str, Any]:
    v2_sensors = [s.id for s in world.sensors() if s.decoder_version == "v2"]
    written: dict[str, list[str]] = {"sessions": [], "schema": []}
    for protocol, _label in PROTOCOLS:
        for sensor_id in (*v2_sensors, HARBOR_BRANCH):
            rows = _rows_for(world, sensor_id, protocol, 6)
            if not rows:
                continue
            sensor = world.sensor(sensor_id)
            name = f"sessions/{protocol}.{sensor.decoder_version}.json"
            if name in written["sessions"]:
                continue
            row = _single_answer_first(world, rows, protocol)[0]
            _write(out / name, world.to_session(row, "analyst").model_dump(mode="json"))
            written["sessions"].append(name)
        schema = world.protocol_schema(protocol)
        if schema is not None:
            name = f"schema/{protocol}.json"
            _write(out / name, schema.model_dump(mode="json"))
            written["schema"].append(name)

    grid_rows: list[dict[str, Any]] = []
    end = world.capture_now_ms()
    start = max(world.data_start_ms, end - WINDOW_HOURS * 3_600_000)
    for sensor in world.sensors():
        for row in world.rows_desc(sensor.id, start, end):
            grid_rows.append(world.to_session_row(row).model_dump(mode="json"))
            if len(grid_rows) >= ROW_SAMPLE:
                break
        if len(grid_rows) >= ROW_SAMPLE:
            break
    _write(out / "rows.json", {"items": grid_rows})
    _write(out / "fields.json", {"items": [f.model_dump(mode="json") for f in FIELD_DEFS]})
    _write(out / "columns.json", {"items": [c.model_dump(mode="json") for c in COLUMN_DEFS]})
    index = {
        "seed": world.seed,
        "sessions": sorted(written["sessions"]),
        "schema": sorted(written["schema"]),
        "rows": "rows.json",
        "fields": "fields.json",
        "columns": "columns.json",
    }
    _write(out / "index.json", index)
    return index


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", default="fixtures", help="world seed (default: fixtures)")
    parser.add_argument("--out", default="fixtures", help="output directory (default: ./fixtures)")


@command(
    "export-fixtures",
    help="Dump one sample payload per protocol to a directory.",
    configure=_configure,
)
def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    try:
        world = build_world_or_explain(args.seed)
        index = export(world, out)
    except WorldUnavailableError as exc:
        print(f"cannot export fixtures: {exc}")
        return EXIT_MISSING_WORLD
    print(f"wrote {len(index['sessions'])} sessions and {len(index['schema'])} schemas into {out}")
    return 0
