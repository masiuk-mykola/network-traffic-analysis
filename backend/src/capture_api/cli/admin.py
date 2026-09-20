import argparse
import json
import sys
from typing import Any

import httpx

from capture_api.cli import command
from capture_api.settings import CHAOS_PROFILES, Settings, get_settings

TIMEOUT_S = 15.0
EXIT_UNREACHABLE = 2
EXIT_REFUSED = 3


def cli_settings() -> Settings:
    return get_settings()


def base_url(args: argparse.Namespace) -> str:
    url = getattr(args, "url", None)
    if url:
        return str(url).rstrip("/")
    settings = cli_settings()
    return f"http://{settings.host}:{settings.port}"


def admin_headers(args: argparse.Namespace) -> dict[str, str]:
    token = getattr(args, "token", None) or cli_settings().admin_token
    return {"X-Admin-Token": token}


def fail(message: str, code: int = EXIT_UNREACHABLE) -> int:
    print(message, file=sys.stderr)
    return code


def call(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    body: Any | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any] | None:
    url = f"{base_url(args)}{path}"
    try:
        response = httpx.request(
            method,
            url,
            headers=admin_headers(args),
            json=body,
            params=params,
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        fail(f"cannot reach {url}: {exc}\nIs `capture-api serve` running?")
        return None
    try:
        payload: Any = response.json() if response.content else None
    except ValueError:
        payload = response.text
    return response.status_code, payload


def report_failure(status: int, payload: Any) -> int:
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    hint = " (wrong CAP_ADMIN_TOKEN?)" if status == 401 else ""
    return fail(f"HTTP {status}{hint}: {detail}", EXIT_REFUSED)


def _overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    fields = {
        "get_503_rate": args.get_503_rate,
        "drop_rate": args.drop_rate,
        "sse_rotate_s": args.sse_rotate_s,
        "access_ttl_s": args.access_ttl_s,
        "live_burst": args.live_burst,
        "latency_ms": (
            [args.latency_ms[0], args.latency_ms[1]] if args.latency_ms is not None else None
        ),
    }
    present = {key: value for key, value in fields.items() if value is not None}
    return present or None


def _run_chaos(args: argparse.Namespace) -> int:
    if args.profile is None:
        result = call(args, "GET", "/v1/__admin/chaos")
    else:
        result = call(
            args,
            "PUT",
            "/v1/__admin/chaos",
            body={"profile": args.profile, "overrides": _overrides(args)},
        )
    if result is None:
        return EXIT_UNREACHABLE
    status, payload = result
    if status >= 400:
        return report_failure(status, payload)
    print(json.dumps(payload, indent=2))
    return 0


def _simple(args: argparse.Namespace, method: str, path: str, body: Any | None, done: str) -> int:
    result = call(args, method, path, body=body)
    if result is None:
        return EXIT_UNREACHABLE
    status, payload = result
    if status >= 400:
        return report_failure(status, payload)
    print(done if payload is None else json.dumps(payload, indent=2))
    return 0


def _run_expire(args: argparse.Namespace) -> int:
    body = {"email": args.email} if args.email else {}
    target = args.email or "every session"
    return _simple(
        args, "POST", "/v1/__admin/expire-tokens", body, f"expired access tokens of {target}"
    )


def _run_revoke(args: argparse.Namespace) -> int:
    return _simple(
        args, "POST", "/v1/__admin/revoke", {"email": args.email}, f"revoked {args.email}"
    )


def _run_touch(args: argparse.Namespace) -> int:
    return _simple(args, "POST", f"/v1/__admin/hunts/{args.hunt_id}/touch", None, "touched")


def _run_reset(args: argparse.Namespace) -> int:
    return _simple(args, "POST", "/v1/__admin/reset", None, "reset: searches, hunts, cases, tokens")


def connection_flags(parser: argparse.ArgumentParser, *, suppress: bool = False) -> None:
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--url", default=default, help="base URL of the running simulator")
    parser.add_argument("--token", default=default, help="admin token (default CAP_ADMIN_TOKEN)")


def _configure(parser: argparse.ArgumentParser) -> None:
    connection_flags(parser)
    actions = parser.add_subparsers(dest="admin_action", metavar="<action>", required=True)

    chaos = actions.add_parser("chaos", help="show or set the chaos profile")
    chaos.add_argument("profile", nargs="?", choices=CHAOS_PROFILES, help="omit to show")
    chaos.add_argument("--get-503-rate", type=float, dest="get_503_rate")
    chaos.add_argument("--drop-rate", type=float, dest="drop_rate")
    chaos.add_argument("--latency-ms", type=int, nargs=2, metavar=("MIN", "MAX"))
    chaos.add_argument("--sse-rotate-s", type=int, dest="sse_rotate_s")
    chaos.add_argument("--access-ttl-s", type=int, dest="access_ttl_s")
    chaos.add_argument("--live-burst", type=int, dest="live_burst")
    connection_flags(chaos, suppress=True)
    chaos.set_defaults(_admin=_run_chaos)

    expire = actions.add_parser("expire-tokens", help="expire live access tokens")
    expire.add_argument("--email", help="only this user (default: everyone)")
    connection_flags(expire, suppress=True)
    expire.set_defaults(_admin=_run_expire)

    revoke = actions.add_parser("revoke", help="revoke a user's sessions")
    revoke.add_argument("--email", required=True)
    connection_flags(revoke, suppress=True)
    revoke.set_defaults(_admin=_run_revoke)

    touch = actions.add_parser("touch-hunt", help="bump a hunt version (forces a 412)")
    touch.add_argument("hunt_id")
    connection_flags(touch, suppress=True)
    touch.set_defaults(_admin=_run_touch)

    reset = actions.add_parser("reset", help="clear searches, hunts, cases, imports, tokens")
    connection_flags(reset, suppress=True)
    reset.set_defaults(_admin=_run_reset)


@command("admin", help="Drive the dev endpoints of a running simulator.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    action: Any = args._admin
    return int(action(args))
