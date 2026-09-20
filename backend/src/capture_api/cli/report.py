import argparse
import json
from typing import Any

from capture_api.cli import command
from capture_api.cli.admin import EXIT_UNREACHABLE, call, connection_flags, report_failure

MARKS: dict[str, str] = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "n/a": " -- "}
ID_WIDTH = 30
VALUE_WIDTH = 8
SEVERITY: dict[str, int] = {"n/a": 0, "pass": 1, "warn": 2, "fail": 3}


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _check_lines(check: dict[str, Any], *, verbose: bool, suffix: str = "") -> list[str]:
    mark = MARKS.get(check.get("status", "n/a"), "????")
    value = _format_value(check.get("value"))
    lines = [
        f"  {mark}  {check.get('id', ''):<{ID_WIDTH}} {value:>{VALUE_WIDTH}}  "
        f"{check.get('threshold', '')}{suffix}"
    ]
    if verbose:
        lines.extend(
            f"        {item.get('t')} {item.get('method')} {item.get('path')} "
            f"-> {item.get('status')}" + (f" — {item['note']}" if item.get("note") else "")
            for item in check.get("evidence", [])
        )
    return lines


def _worst_per_check(
    families: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    worst: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    order: list[str] = []
    for family in families:
        for check in family.get("checks", []):
            check_id = str(check.get("id", ""))
            if check_id not in worst:
                order.append(check_id)
                worst[check_id] = (check, family)
                continue
            current, _ = worst[check_id]
            if SEVERITY.get(check.get("status", "n/a"), 0) > SEVERITY.get(
                current.get("status", "n/a"), 0
            ):
                worst[check_id] = (check, family)
    return [worst[check_id] for check_id in order]


def render(report: dict[str, Any], *, verbose: bool = True, per_family: bool = False) -> str:
    summary = report.get("summary", {})
    lines = [
        f"Capture API observer — seed {report.get('seed')} · chaos {report.get('profile')} · "
        f"{summary.get('pass', 0)} pass / {summary.get('warn', 0)} warn / "
        f"{summary.get('fail', 0)} fail",
    ]
    families = report.get("families") or []
    if not families:
        lines.append("")
        lines.append("No traffic recorded yet — sign in through your console and use it.")
        return "\n".join(lines)

    if per_family:
        for family in families:
            lines.append("")
            lines.append(
                f"{family.get('user')}  [{family.get('family_id')}]  "
                f"{family.get('requests')} requests"
            )
            for check in family.get("checks", []):
                lines.extend(_check_lines(check, verbose=verbose))
        return "\n".join(lines)

    requests = sum(int(family.get("requests") or 0) for family in families)
    lines.append(
        f"{len(families)} token famil{'y' if len(families) == 1 else 'ies'}, "
        f"{requests} requests — worst status per check"
    )
    lines.append("")
    for check, family in _worst_per_check(families):
        suffix = (
            f"   [{family.get('user')}]"
            if check.get("status") in ("warn", "fail") and len(families) > 1
            else ""
        )
        lines.extend(_check_lines(check, verbose=verbose, suffix=suffix))
    if len(families) > 1:
        lines.append("")
        lines.append("Run `capture-api report --all` for the per-family breakdown.")
    return "\n".join(lines)


def _configure(parser: argparse.ArgumentParser) -> None:
    connection_flags(parser)
    parser.add_argument("--family-id", help="only this token family")
    parser.add_argument("--since", help="seconds ago (e.g. 600) or an ISO-8601 instant")
    parser.add_argument("--json", action="store_true", help="print the raw JSON document")
    parser.add_argument("--quiet", action="store_true", help="hide the evidence lines")
    parser.add_argument(
        "--all", action="store_true", help="one block per token family instead of the merged view"
    )


@command("report", help="Print the observer's client-behaviour report.", configure=_configure)
def run(args: argparse.Namespace) -> int:
    params = {
        key: value for key, value in (("family_id", args.family_id), ("since", args.since)) if value
    }
    result = call(args, "GET", "/v1/__observer/report", params=params or None)
    if result is None:
        return EXIT_UNREACHABLE
    status, payload = result
    if status >= 400:
        return report_failure(status, payload)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(render(payload, verbose=not args.quiet, per_family=args.all))
    return 0
