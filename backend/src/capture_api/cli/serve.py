import argparse
import os

import uvicorn

from capture_api.cli import command
from capture_api.settings import CHAOS_PROFILES, get_settings


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", help="bind address (CAP_HOST, default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (CAP_PORT, default 8700)")
    parser.add_argument("--seed", help="world seed (CAP_SEED, default 'demo')")
    parser.add_argument("--chaos", choices=CHAOS_PROFILES, help="initial chaos profile (CAP_CHAOS)")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")


@command("serve", help="Run the simulator HTTP server.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    overrides = {"CAP_HOST": args.host, "CAP_PORT": args.port, "CAP_SEED": args.seed}
    overrides["CAP_CHAOS"] = args.chaos
    for key, value in overrides.items():
        if value is not None:
            os.environ[key] = str(value)
    get_settings.cache_clear()
    settings = get_settings()
    uvicorn.run(
        "capture_api.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=bool(args.reload),
        log_level=settings.log_level,
        timeout_graceful_shutdown=3,
    )
    return 0
