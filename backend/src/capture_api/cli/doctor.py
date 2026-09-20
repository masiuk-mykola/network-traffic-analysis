import argparse
import shutil
import socket
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from capture_api.cli import command
from capture_api.cli.admin import base_url

type Level = Literal["ok", "warn", "fail"]

MARKS: dict[str, str] = {"ok": "  ok  ", "warn": " warn ", "fail": " FAIL "}
TOOLS: tuple[tuple[str, tuple[str, ...], bool], ...] = (("uv", ("uv", "--version"), True),)
MIN_PYTHON = (3, 12)


@dataclass(frozen=True, slots=True)
class Result:
    level: Level
    name: str
    detail: str


def _python() -> Result:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info[:2] < MIN_PYTHON:
        return Result("fail", "python", f"{version} (3.12+ required)")
    return Result("ok", "python", version)


def _tool(name: str, argv: tuple[str, ...], required: bool) -> Result:
    if shutil.which(argv[0]) is None:
        return Result(
            "fail" if required else "warn", name, "not installed (see the README quick start)"
        )
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)  # noqa: S603
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - exotic
        return Result("warn", name, f"could not run: {exc}")
    lines = (out.stdout or out.stderr).strip().splitlines() or ["(no version output)"]
    return Result("ok", name, lines[0])


def _port(port: int, what: str, *, ours: bool = False) -> Result:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.4)
        busy = client.connect_ex(("127.0.0.1", port)) == 0
    if busy and ours:
        return Result("ok", f"port {port}", f"in use by the {what}, which is answering")
    if busy:
        return Result("warn", f"port {port}", f"already in use — the {what} may be running")
    return Result("ok", f"port {port}", f"free for the {what}")


def _simulator_port(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _backend(url: str) -> tuple[Result, dict[str, Any] | None]:
    try:
        response = httpx.get(f"{url}/v1/health", timeout=5.0)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return Result("warn", "simulator", f"not reachable at {url} ({exc})"), None
    status = payload.get("status")
    degraded = [
        name
        for name, component in (payload.get("components") or {}).items()
        if component.get("status") != "ok"
    ]
    detail = f"{url} — {status}, version {payload.get('version')}"
    if degraded:
        detail += f", degraded: {', '.join(degraded)}"
    return Result("ok" if status == "ok" else "warn", "simulator", detail), payload


def diagnose(url: str) -> Iterator[Result]:
    yield _python()
    for name, argv, required in TOOLS:
        yield _tool(name, argv, required)
    backend, payload = _backend(url)
    yield _port(_simulator_port(url), "simulator", ours=payload is not None)
    yield backend


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--url", help="base URL of the simulator (default http://CAP_HOST:CAP_PORT)"
    )


@command("doctor", help="Check the toolchain, ports and reachability.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    url = base_url(args)
    worst: Level = "ok"
    for result in diagnose(url):
        print(f"[{MARKS[result.level]}] {result.name:<12} {result.detail}")
        if result.level == "fail" or (result.level == "warn" and worst == "ok"):
            worst = result.level
    return 1 if worst == "fail" else 0
