import html
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from capture_api.api.admin import AdminGuard, admin_token
from capture_api.deps import SettingsDep
from capture_api.domain.base import iso_ms
from capture_api.domain.models import (
    CheckStatus,
    ObserverCheck,
    ObserverEvidence,
    ObserverFamily,
    ObserverReport,
    ObserverSummary,
)
from capture_api.errors import DomainError
from capture_api.platform.chaos import ChaosController
from capture_api.platform.observer import (
    FamilyLog,
    Observer,
    RequestRecord,
    StreamRecord,
    is_download,
)
from capture_api.settings import Settings

router = APIRouter(tags=["observer"], include_in_schema=False)
root_router = APIRouter(tags=["observer"], include_in_schema=False)

MAX_EVIDENCE = 5
AUTH_FREE_4XX: frozenset[int] = frozenset({401, 408, 409, 425, 429})
DEDUPE_WINDOW_S = 0.1
RETRY_4XX_WINDOW_S = 5.0
DOWNLOAD_WINDOW_S = 5.0
REFRESH_FLIGHT_S = 2.0
LOGOUT_GRACE_S = 5.0
DUPLICATE_JOB_WINDOW_S = 10.0
ABANDONED_AFTER_S = 60.0
SSE_MIN_GAP_S = 1.0
ENRICH_BURST_S = 1.0
ENRICH_BURST = 5
MAX_LIMIT = 500


@dataclass(frozen=True, slots=True)
class Evaluation:
    status: CheckStatus
    value: int | float | str | None = None
    evidence: tuple[ObserverEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckContext:
    family: FamilyLog
    requests: tuple[RequestRecord, ...]
    streams: tuple[StreamRecord, ...]
    now: float

    def where(self, predicate: Callable[[RequestRecord], bool]) -> list[RequestRecord]:
        return [record for record in self.requests if predicate(record)]

    def with_code(self, *codes: str) -> list[RequestRecord]:
        wanted = set(codes)
        return [record for record in self.requests if record.error_code in wanted]

    def events(self, *kinds: str) -> list[StreamRecord]:
        wanted = set(kinds)
        return [event for event in self.streams if event.kind in wanted]


@dataclass(frozen=True, slots=True)
class CheckSpec:
    id: str
    label: str
    threshold: str
    evaluate: Callable[[CheckContext], Evaluation]
    stretch: bool = False


NA = Evaluation("n/a")


def _evidence(record: RequestRecord, note: str | None = None) -> ObserverEvidence:
    return ObserverEvidence(
        t=record.t_iso,
        method=record.method,
        path=record.path + (f"?{record.query}" if record.query else ""),
        status=record.status,
        note=note,
    )


def _stream_evidence(event: StreamRecord, note: str) -> ObserverEvidence:
    return ObserverEvidence(
        t=event.t_iso,
        method="STREAM",
        path=event.kind,
        status=event.code or 0,
        note=note,
    )


def _verdict(
    offenders: Sequence[ObserverEvidence],
    *,
    value: int | float | str | None = None,
    failing: CheckStatus = "fail",
) -> Evaluation:
    count = len(offenders) if value is None else value
    status: CheckStatus = "pass" if not offenders else failing
    return Evaluation(status, count, tuple(offenders[:MAX_EVIDENCE]))


def _zero_count(records: Sequence[RequestRecord], note: str) -> Evaluation:
    return Evaluation(
        "pass" if not records else "fail",
        len(records),
        tuple(_evidence(record, note) for record in records[:MAX_EVIDENCE]),
    )


def _refresh_single_flight(ctx: CheckContext) -> Evaluation:
    refreshes = ctx.where(lambda r: r.path == "/v1/auth/refresh")
    if not refreshes:
        return NA
    offenders = [
        _evidence(later, f"{later.t_mono - earlier.t_mono:.2f}s after the previous refresh")
        for earlier, later in pairwise(refreshes)
        if later.t_mono - earlier.t_mono < REFRESH_FLIGHT_S
    ]
    return _verdict(offenders)


def _refresh_reuse(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: r.path == "/v1/auth/refresh"):
        return NA
    return _zero_count(ctx.with_code("refresh_reused"), "a consumed refresh token was replayed")


def _logout_once(ctx: CheckContext) -> Evaluation:
    revoked_at: float | None = None
    for record in ctx.requests:
        logged_out = record.path == "/v1/auth/logout" and record.status == 204
        if logged_out or record.error_code == "session_revoked":
            revoked_at = record.t_mono
            break
    if revoked_at is None:
        return NA
    late = [
        record
        for record in ctx.requests
        if record.has_authorization
        and record.t_mono > revoked_at + LOGOUT_GRACE_S
        and not record.path.startswith("/v1/auth/")
    ]
    return _zero_count(late, "sent with a token of a revoked session")


def _bearer_from_browser(ctx: CheckContext) -> Evaluation:
    offenders = ctx.where(
        lambda r: r.has_authorization and bool(r.origin) and str(r.origin).startswith("http")
    )
    if not ctx.where(lambda r: bool(r.origin)):
        return NA
    return _zero_count(offenders, "Authorization sent together with a browser Origin")


def _duplicate_jobs(ctx: CheckContext) -> Evaluation:
    creations = ctx.where(
        lambda r: r.method == "POST" and r.path == "/v1/searches" and r.status in (200, 202)
    )
    if len(creations) < 2:
        return NA
    offenders: list[ObserverEvidence] = []
    for index, later in enumerate(creations):
        for earlier in creations[:index]:
            same_body = later.body_hash is not None and later.body_hash == earlier.body_hash
            if (
                same_body
                and not later.replayed
                and later.t_mono - earlier.t_mono < DUPLICATE_JOB_WINDOW_S
            ):
                offenders.append(_evidence(later, "identical search body within 10 s"))
                break
    return _verdict(offenders)


def _abandoned_searches(ctx: CheckContext) -> Evaluation:
    creations = [
        record
        for record in ctx.requests
        if record.method == "POST" and record.path == "/v1/searches" and record.resource_id
    ]
    if not creations:
        return NA
    deletes = {
        record.path.rsplit("/", 1)[-1]: record.t_mono
        for record in ctx.requests
        if record.method == "DELETE" and record.path.startswith("/v1/searches/")
    }
    offenders: list[ObserverEvidence] = []
    for index, creation in enumerate(creations[:-1]):
        successor = creations[index + 1]
        if ctx.now - successor.t_mono <= ABANDONED_AFTER_S:
            continue
        deleted_at = deletes.get(str(creation.resource_id))
        if deleted_at is None or deleted_at > successor.t_mono + ABANDONED_AFTER_S:
            offenders.append(
                _evidence(creation, f"search {creation.resource_id} was never cancelled")
            )
    return _verdict(offenders)


def _slots_exhausted(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: r.path == "/v1/searches" and r.method == "POST"):
        return NA
    return _zero_count(ctx.with_code("too_many_searches"), "all three search slots were busy")


def _retry_after_violations(ctx: CheckContext) -> Evaluation:
    blocked: dict[str, tuple[float, RequestRecord]] = {}
    offenders: list[ObserverEvidence] = []
    seen_limit = False
    for record in ctx.requests:
        entry = blocked.get(record.route)
        if entry is not None and record.t_mono < entry[0]:
            offenders.append(
                _evidence(
                    record,
                    f"retried {record.t_mono - entry[1].t_mono:.2f}s after a "
                    f"{entry[1].status} asking for {entry[1].retry_after_s:.0f}s",
                )
            )
        if record.status in (429, 503) and record.retry_after_s:
            seen_limit = True
            blocked[record.route] = (record.t_mono + record.retry_after_s, record)
    if not seen_limit:
        return NA
    return _verdict(offenders)


def _retried_4xx(ctx: CheckContext) -> Evaluation:
    refused = [
        record
        for record in ctx.requests
        if 400 <= record.status < 500 and record.status not in AUTH_FREE_4XX
    ]
    if not refused:
        return NA
    offenders: list[ObserverEvidence] = []
    for record in refused:
        repeat = next(
            (
                later
                for later in ctx.requests
                if later.seq > record.seq
                and later.key == record.key
                and later.t_mono - record.t_mono < RETRY_4XX_WINDOW_S
            ),
            None,
        )
        if repeat is not None:
            offenders.append(_evidence(repeat, f"repeated a {record.status} within 5 s"))
    return _verdict(offenders)


def _get_dedupe(ctx: CheckContext) -> Evaluation:
    gets = ctx.where(lambda r: r.method == "GET")
    if not gets:
        return NA
    worst = 1
    offender: RequestRecord | None = None
    for index, record in enumerate(gets):
        burst = [
            other
            for other in gets[index:]
            if other.key == record.key and other.t_mono - record.t_mono <= DEDUPE_WINDOW_S
        ]
        if len(burst) > worst:
            worst, offender = len(burst), record
    status: CheckStatus = "pass" if worst <= 2 else ("warn" if worst < 5 else "fail")
    evidence = (_evidence(offender, f"{worst} identical GETs within 100 ms"),) if offender else ()
    return Evaluation(status, worst, evidence)


def _invalid_cursor(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: "cursor" in r.query):
        return NA
    return _zero_count(
        ctx.with_code("invalid_cursor", "cursor_sort_mismatch"),
        "a cursor was tampered with or reused with another sort",
    )


def _limit_over_max(ctx: CheckContext) -> Evaluation:
    with_limit = ctx.where(lambda r: r.limit_param is not None)
    if not with_limit:
        return NA
    over = [record for record in with_limit if (record.limit_param or 0) > MAX_LIMIT]
    largest = max((record.limit_param or 0) for record in with_limit)
    return _verdict(
        [_evidence(record, f"limit={record.limit_param} is silently clamped") for record in over],
        value=largest,
        failing="warn",
    )


def _health_interval(ctx: CheckContext) -> Evaluation:
    polls = ctx.where(lambda r: r.path == "/v1/health")
    if len(polls) < 2:
        return NA
    gaps = [b.t_mono - a.t_mono for a, b in pairwise(polls)]
    median = statistics.median(gaps)
    status: CheckStatus = "pass" if median >= 10 else ("warn" if median >= 5 else "fail")
    evidence = () if status == "pass" else (_evidence(polls[-1], f"median gap {median:.1f}s"),)
    return Evaluation(status, round(median, 2), evidence)


def _estimate_rate(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: r.path == "/v1/estimate"):
        return NA
    return _zero_count(ctx.with_code("estimate_rate_limited"), "more than 4 estimates per second")


def _sse_double_open(ctx: CheckContext) -> Evaluation:
    opens = ctx.events("sse_open")
    if not opens:
        return NA
    offenders = [
        _stream_evidence(later, f"opened {later.t_mono - earlier.t_mono:.2f}s after the previous")
        for earlier, later in pairwise(opens)
        if later.t_mono - earlier.t_mono < SSE_MIN_GAP_S
    ]
    return _verdict(offenders)


def _sse_resume(ctx: CheckContext) -> Evaluation:
    opens = ctx.events("sse_open")
    if len(opens) < 2:
        return NA
    reopens = opens[1:]
    resumed = [event for event in reopens if event.resume_from is not None]
    ratio = len(resumed) / len(reopens)
    status: CheckStatus = "pass" if ratio >= 0.95 else ("warn" if ratio >= 0.8 else "fail")
    blind = [event for event in reopens if event.resume_from is None]
    evidence = tuple(
        _stream_evidence(event, "re-opened without Last-Event-ID") for event in blind[:MAX_EVIDENCE]
    )
    return Evaluation(status, f"{ratio * 100:.0f}%", evidence)


def _sse_reconnect_backoff(ctx: CheckContext) -> Evaluation:
    events = ctx.events("sse_open", "sse_close")
    closes = [event for event in events if event.kind == "sse_close"]
    if not closes:
        return NA
    offenders: list[ObserverEvidence] = []
    for event in events:
        if event.kind != "sse_open":
            continue
        previous = [close for close in closes if close.t_mono <= event.t_mono]
        if previous and event.t_mono - previous[-1].t_mono < SSE_MIN_GAP_S:
            offenders.append(
                _stream_evidence(
                    event, f"re-opened {event.t_mono - previous[-1].t_mono:.2f}s after a close"
                )
            )
    return _verdict(offenders)


def _if_match(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: r.method == "PATCH"):
        return NA
    return _zero_count(
        ctx.where(lambda r: r.status == 428), "PATCH without If-Match (428 precondition_required)"
    )


def _minimal_patch(ctx: CheckContext) -> Evaluation:
    patches = ctx.where(lambda r: r.method == "PATCH" and bool(r.body_keys))
    if not patches:
        return NA
    offenders: list[ObserverEvidence] = []
    for patch in patches:
        known = [
            record
            for record in ctx.requests
            if record.seq < patch.seq and record.path == patch.path and record.resource_fields
        ]
        if not known:
            continue
        current = known[-1].resource_fields
        unchanged = [
            key
            for key, digest in patch.body_fields.items()
            if key in current and current[key] == digest
        ]
        if unchanged:
            offenders.append(
                _evidence(patch, f"resent unchanged field(s): {', '.join(sorted(unchanged))}")
            )
    return _verdict(offenders, failing="warn")


def _download_single_request(ctx: CheckContext) -> Evaluation:
    downloads = ctx.where(is_download)
    if not downloads:
        return NA
    offenders: list[ObserverEvidence] = []
    for index, record in enumerate(downloads):
        burst = [
            other
            for other in downloads[index:]
            if other.path == record.path and other.t_mono - record.t_mono <= DOWNLOAD_WINDOW_S
        ]
        if len(burst) > 2:
            offenders.append(_evidence(record, f"{len(burst)} requests for the same file in 5 s"))
    return _verdict(offenders)


def _ws_pong_ok(ctx: CheckContext) -> Evaluation:
    closes = ctx.events("ws_close")
    if not ctx.events("ws_open"):
        return NA
    missed = [event for event in closes if event.code == 4408]
    return _verdict(
        [_stream_evidence(event, "closed 4408: the client missed a pong") for event in missed]
    )


def _ws_ticket_reuse(ctx: CheckContext) -> Evaluation:
    rejects = ctx.events("ws_rejected")
    if not ctx.events("ws_open") and not rejects:
        return NA
    reused = [event for event in rejects if event.reason == "ticket_reuse"]
    return _verdict([_stream_evidence(event, "live ticket presented twice") for event in reused])


def _ws_resubscribe(ctx: CheckContext) -> Evaluation:
    opens = ctx.events("ws_open")
    if not opens:
        return NA
    subscribes = ctx.events("ws_subscribe")
    offenders = [
        _stream_evidence(event, "no subscribe within 5 s of the handshake")
        for event in opens
        if not any(0 <= sub.t_mono - event.t_mono <= 5.0 for sub in subscribes)
    ]
    return _verdict(offenders)


def _enrich_per_ip_storm(ctx: CheckContext) -> Evaluation:
    singles = ctx.where(lambda r: r.path.startswith("/v1/enrich/ips/"))
    if not singles:
        return NA
    offenders: list[ObserverEvidence] = []
    for index, record in enumerate(singles):
        burst = [
            other for other in singles[index:] if other.t_mono - record.t_mono <= ENRICH_BURST_S
        ]
        if len(burst) >= ENRICH_BURST:
            offenders.append(
                _evidence(record, f"{len(burst)} single-IP lookups in 1 s; use POST /v1/enrich/ips")
            )
            break
    return _verdict(offenders)


def _import_checksum(ctx: CheckContext) -> Evaluation:
    if not ctx.where(lambda r: r.method == "POST" and r.path == "/v1/imports"):
        return NA
    return _zero_count(
        ctx.with_code("checksum_mismatch"), "the uploaded bytes did not match sha256"
    )


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "auth.refresh_single_flight",
        "One refresh in flight",
        "no two refreshes within 2 s",
        _refresh_single_flight,
    ),
    CheckSpec("auth.refresh_reuse", "No refresh reuse", "0 refresh_reused", _refresh_reuse),
    CheckSpec(
        "auth.logout_once",
        "Stops using revoked tokens",
        "no authenticated call > 5 s after revocation",
        _logout_once,
    ),
    CheckSpec(
        "auth.bearer_from_browser",
        "Tokens stay server-side",
        "0 requests with Authorization + browser Origin",
        _bearer_from_browser,
    ),
    CheckSpec(
        "search.duplicate_jobs",
        "No duplicate search jobs",
        "0 identical search bodies within 10 s",
        _duplicate_jobs,
    ),
    CheckSpec(
        "search.abandoned",
        "Searches are cancelled",
        "0 superseded searches left running > 60 s",
        _abandoned_searches,
    ),
    CheckSpec(
        "search.slots_exhausted", "Search slots free", "0 too_many_searches", _slots_exhausted
    ),
    CheckSpec(
        "http.retry_after_violations",
        "Retry-After honoured",
        "0 retries before the advertised delay",
        _retry_after_violations,
    ),
    CheckSpec(
        "http.retried_4xx",
        "No blind 4xx retries",
        "0 identical requests within 5 s of a 4xx",
        _retried_4xx,
    ),
    CheckSpec(
        "http.get_dedupe",
        "Requests are de-duplicated",
        "at most 2 identical GETs within 100 ms",
        _get_dedupe,
    ),
    CheckSpec("http.invalid_cursor", "Cursors used verbatim", "0 invalid_cursor", _invalid_cursor),
    CheckSpec(
        "http.limit_over_max", "limit within the maximum", "no limit above 500", _limit_over_max
    ),
    CheckSpec(
        "poll.health_interval", "Health polling is calm", "median gap >= 10 s", _health_interval
    ),
    CheckSpec(
        "estimate.rate", "Estimates are throttled", "0 estimate_rate_limited", _estimate_rate
    ),
    CheckSpec("sse.double_open", "One live stream", "no two streams within 1 s", _sse_double_open),
    CheckSpec(
        "sse.resume", "Streams resume", ">= 95 % of re-opens carry a resume point", _sse_resume
    ),
    CheckSpec(
        "sse.reconnect_backoff",
        "Reconnects back off",
        "no re-open within 1 s of a close",
        _sse_reconnect_backoff,
    ),
    CheckSpec("concurrency.if_match", "PATCH sends If-Match", "0 responses with 428", _if_match),
    CheckSpec(
        "concurrency.minimal_patch",
        "PATCH bodies are minimal",
        "no unchanged fields resent",
        _minimal_patch,
    ),
    CheckSpec(
        "download.single_request",
        "Downloads happen once",
        "at most 2 requests per file within 5 s",
        _download_single_request,
    ),
    CheckSpec("ws.pong_ok", "WebSocket answers pings", "0 closes with 4408", _ws_pong_ok, True),
    CheckSpec(
        "ws.ticket_reuse", "Live tickets used once", "0 reused tickets", _ws_ticket_reuse, True
    ),
    CheckSpec(
        "ws.resubscribe",
        "Re-subscribes after reconnect",
        "a subscribe within 5 s of every handshake",
        _ws_resubscribe,
        True,
    ),
    CheckSpec(
        "enrich.per_ip_storm",
        "Enrichment is batched",
        "no 5 single-IP lookups within 1 s",
        _enrich_per_ip_storm,
        True,
    ),
    CheckSpec(
        "import.checksum_mismatch",
        "Uploads match their checksum",
        "0 checksum_mismatch",
        _import_checksum,
        True,
    ),
)

CHECKS_BY_ID = {spec.id: spec for spec in CHECKS}


def _parse_since(since: str | None, now: float) -> tuple[float | None, str | None]:
    if since is None:
        return None, None
    try:
        return now - float(since), None
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(since)
    except ValueError as exc:
        raise DomainError(
            422, "bad_since", "since must be seconds (e.g. 300) or an ISO-8601 instant."
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return None, iso_ms(moment)


def _context(family: FamilyLog, now: float, since: tuple[float | None, str | None]) -> CheckContext:
    mono_from, iso_from = since

    def keep(t_mono: float, t_iso: str) -> bool:
        return (mono_from is None or t_mono >= mono_from) and (
            iso_from is None or t_iso >= iso_from
        )

    return CheckContext(
        family=family,
        requests=tuple(r for r in family.requests if keep(r.t_mono, r.t_iso)),
        streams=tuple(s for s in family.streams if keep(s.t_mono, s.t_iso)),
        now=now,
    )


def evaluate_family(ctx: CheckContext) -> list[ObserverCheck]:
    checks: list[ObserverCheck] = []
    for spec in CHECKS:
        outcome = spec.evaluate(ctx)
        checks.append(
            ObserverCheck(
                id=spec.id,
                label=spec.label,
                value=outcome.value,
                threshold=spec.threshold,
                status=outcome.status,
                evidence=list(outcome.evidence[:MAX_EVIDENCE]),
            )
        )
    return checks


def build_report(
    observer: Observer,
    settings: Settings,
    *,
    profile: str,
    family_id: str | None = None,
    since: str | None = None,
) -> ObserverReport:
    now = observer.time_source.monotonic()
    window = _parse_since(since, now)
    families = [
        family
        for family in observer.families()
        if family_id is None or family.family_id == family_id
    ]
    families.sort(key=lambda f: f.requests[-1].t_mono if f.requests else 0.0, reverse=True)
    rendered: list[ObserverFamily] = []
    totals: dict[str, int] = {"pass": 0, "warn": 0, "fail": 0}
    for family in families:
        ctx = _context(family, now, window)
        checks = evaluate_family(ctx)
        for check in checks:
            if check.status in totals:
                totals[check.status] += 1
        rendered.append(
            ObserverFamily(
                family_id=family.family_id,
                user=family.user,
                requests=len(ctx.requests),
                checks=checks,
            )
        )
    return ObserverReport(
        generated_at=datetime.fromtimestamp(observer.time_source.time(), tz=UTC),
        seed=settings.seed,
        profile=profile,
        full_history=settings.full_history,
        families=rendered,
        summary=ObserverSummary(pass_=totals["pass"], warn=totals["warn"], fail=totals["fail"]),
    )


def _observer_of(request: Request) -> Observer:
    observer = getattr(request.app.state, "observer", None)
    if not isinstance(observer, Observer):
        raise DomainError.unavailable(
            "observer_unavailable", "The observer is not recording yet.", 5
        )
    return observer


def _profile_of(request: Request) -> str:
    controller = getattr(request.app.state, "chaos", None)
    return controller.profile if isinstance(controller, ChaosController) else "calm"


FamilyQuery = Annotated[str | None, Query(description="Only this token family.")]
SinceQuery = Annotated[
    str | None, Query(description="Seconds ago (e.g. 600) or an ISO-8601 instant.")
]


@router.get(
    "/__observer/report",
    summary="Client-behaviour report",
    dependencies=[AdminGuard],
)
async def get_observer_report(
    request: Request,
    settings: SettingsDep,
    family_id: FamilyQuery = None,
    since: SinceQuery = None,
) -> ObserverReport:
    return build_report(
        _observer_of(request),
        settings,
        profile=_profile_of(request),
        family_id=family_id,
        since=since,
    )


_STYLE = """
:root { color-scheme: light dark; }
body { font: 14px/1.45 ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 24px;
       background: #0f1115; color: #e6e8eb; }
h1 { font-size: 20px; margin: 0 0 4px; }
p.meta { color: #9aa4b2; margin: 0 0 20px; }
section { margin-bottom: 28px; }
h2 { font-size: 15px; margin: 0 0 8px; font-weight: 600; }
table { border-collapse: collapse; width: 100%; max-width: 1100px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #242a33;
         vertical-align: top; }
th { color: #9aa4b2; font-weight: 500; font-size: 12px; text-transform: uppercase;
     letter-spacing: .04em; }
td.status { font-weight: 600; white-space: nowrap; }
tr.pass td.status { color: #4ade80; }
tr.warn td.status { color: #fbbf24; }
tr.fail td.status { color: #f87171; }
tr.na td.status, tr.na td { color: #6b7280; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
ul.evidence { margin: 4px 0 0; padding-left: 16px; color: #9aa4b2; font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px;
         margin-right: 6px; background: #1b2430; }
"""


def _render_evidence(check: ObserverCheck) -> str:
    if not check.evidence:
        return ""
    items = "".join(
        "<li><code>{t}</code> {method} {path} &rarr; {status}{note}</li>".format(
            t=html.escape(item.t),
            method=html.escape(item.method),
            path=html.escape(item.path),
            status=item.status,
            note=f" — {html.escape(item.note)}" if item.note else "",
        )
        for item in check.evidence
    )
    return f'<ul class="evidence">{items}</ul>'


def _render_family(family: ObserverFamily) -> str:
    rows = "".join(
        "<tr class='{cls}'><td class='status'>{status}</td><td><code>{id}</code><br>{label}</td>"
        "<td>{value}</td><td>{threshold}{evidence}</td></tr>".format(
            cls=check.status.replace("/", ""),
            status=html.escape(check.status.upper()),
            id=html.escape(check.id),
            label=html.escape(check.label),
            value=html.escape("" if check.value is None else str(check.value)),
            threshold=html.escape(check.threshold),
            evidence=_render_evidence(check),
        )
        for check in family.checks
    )
    return (
        f"<section><h2>{html.escape(family.user)} "
        f"<span class='badge'>{html.escape(family.family_id)}</span>"
        f"<span class='badge'>{family.requests} requests</span></h2>"
        "<table><thead><tr><th>Status</th><th>Check</th><th>Value</th>"
        f"<th>Threshold</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def render_report_html(report: ObserverReport) -> str:
    families = "".join(_render_family(family) for family in report.families) or (
        "<p class='meta'>No traffic recorded yet. Sign in from your app and use it.</p>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='5'>"
        "<title>Capture API observer</title>"
        f"<style>{_STYLE}</style></head><body>"
        "<h1>Capture API client-behaviour report</h1>"
        f"<p class='meta'>seed <code>{html.escape(report.seed)}</code> &middot; chaos "
        f"<code>{html.escape(report.profile)}</code> &middot; generated "
        f"{html.escape(iso_ms(report.generated_at))} &middot; "
        f"<span class='badge'>{report.summary.pass_} pass</span>"
        f"<span class='badge'>{report.summary.warn} warn</span>"
        f"<span class='badge'>{report.summary.fail} fail</span></p>"
        f"{families}</body></html>"
    )


async def _require_page_token(request: Request, settings: SettingsDep) -> None:
    presented = admin_token(request)
    if presented != settings.admin_token:
        raise DomainError(
            401,
            "admin_token_invalid",
            "Open /__observer?token=$CAP_ADMIN_TOKEN (or send X-Admin-Token).",
        )


@root_router.get(
    "/__observer",
    summary="Client-behaviour report (HTML)",
    response_class=HTMLResponse,
    dependencies=[Depends(_require_page_token)],
)
async def get_observer_page(
    request: Request,
    settings: SettingsDep,
    family_id: FamilyQuery = None,
    since: SinceQuery = None,
    _token: Annotated[str | None, Query(alias="token", description="CAP_ADMIN_TOKEN")] = None,
) -> HTMLResponse:
    report = build_report(
        _observer_of(request),
        settings,
        profile=_profile_of(request),
        family_id=family_id,
        since=since,
    )
    return HTMLResponse(render_report_html(report))


def check_ids() -> Iterable[str]:
    return (spec.id for spec in CHECKS)
