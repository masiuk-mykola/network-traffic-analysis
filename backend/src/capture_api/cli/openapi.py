import argparse
import json
import sys
from pathlib import Path
from typing import Any

from capture_api.cli import command


def _default_out() -> Path:
    root = Path(__file__).resolve().parents[3]
    if (root / "pyproject.toml").is_file():
        return root / "openapi.json"
    return Path.cwd() / "openapi.json"


DEFAULT_OUT = _default_out()


def render_openapi() -> str:
    from capture_api.main import create_app  # noqa: PLC0415 - keep CLI start-up light
    from capture_api.settings import Settings  # noqa: PLC0415

    schema: dict[str, Any] = create_app(Settings()).openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="output path, or '-' for stdout (default: backend/openapi.json)",
    )


@command("openapi", help="Write the OpenAPI document.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    text = render_openapi()
    if args.out == "-":
        sys.stdout.write(text)
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0
