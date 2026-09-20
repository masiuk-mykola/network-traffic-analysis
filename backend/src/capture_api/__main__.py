import argparse
from collections.abc import Sequence

from capture_api import __version__
from capture_api.cli import discover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_api", description="Capture API traffic simulator."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for name, cmd in discover().items():
        sub = subparsers.add_parser(name, help=cmd.help, description=cmd.help)
        cmd.configure(sub)
        sub.set_defaults(_run=cmd.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args._run(args))


if __name__ == "__main__":
    raise SystemExit(main())
