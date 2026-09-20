---
name: http-discipline
description: Use whenever you touch anything that talks to the capture API — a fetch, a React Query hook, a route handler, auth/refresh/logout, polling, pagination, retries, or search jobs. The backend grades the client's HTTP behaviour (`capture-api report`) and these are the rules it scores; read this before writing the code, not after a FAIL.
---

# HTTP discipline — the rules the backend scores

The API in `../backend` watches how this client behaves and issues PASS/WARN/FAIL per check
(`capture-api report`). The rules below are requirements. `SETUP.md` section 5a is the same list in
Ukrainian with more context.

## The invariants

| Rule | What the code must do | Check |
|---|---|---|
| One refresh at a time | Access tokens live 90 s (15 s under `--chaos expiring-tokens`). Refresh is single-use with no grace period — presenting a burnt token revokes the whole family. Every concurrent 401 waits on one in-flight promise per family (`src/lib/api/session-store.ts`). | `auth.refresh_single_flight`, `auth.refresh_reuse` |
| Silence after logout | No authorized request later than 5 s after revocation: cancel in-flight queries, close streams, clear the Query cache. | `auth.logout_once` |
| Tokens stay server-side | `Authorization` must never ride on a request that carries a browser `Origin`. The browser gets an opaque session cookie; every call goes through a route handler. | `auth.bearer_from_browser` |
| No duplicate GETs | At most two identical GETs per 100 ms (five is a FAIL). One `queryKey` shape per resource, no raw `fetch` past React Query. | `http.get_dedupe` |
| Retry with a reason | Never retry a 4xx blindly. Honour `Retry-After` — **an HTTP-date on login**, seconds everywhere else. Login also rate-limits at 5 failures per 60 s per email. | `http.retry_after_violations`, `http.retried_4xx` |
| Cursors verbatim | Pass the cursor back exactly as received; never parse or rebuild it. Keep `limit` ≤ 500 — above that the server clamps and sets `X-Limit-Applied` (a WARN). | `http.invalid_cursor`, `http.limit_over_max` |
| Calm polling | `/v1/health` at most once per 10 s. Search progress polls with backoff, not every frame. | `poll.health_interval` |
| Clean up searches | Three slots per user; over that the API answers 429 `too_many_searches` with `Retry-After: 5` (seconds). `DELETE /v1/searches/{id}` whatever you supersede, and send `Idempotency-Key` on `POST /v1/searches` so a retry after a 503 does not create a twin. | `search.duplicate_jobs`, `search.abandoned`, `search.slots_exhausted` |

`Idempotency-Key` is not declared in `openapi.json`, so the generated types do not know about it — set
the header by hand. Format `^[A-Za-z0-9_-]{8,64}$`, replay window 10 minutes, a replayed response comes
back with `Idempotent-Replayed: true`.

## Optional features bring their own checks

There are 25 checks in total. Taking on an optional feature means taking on its checks: SSE
(`sse.double_open`, `sse.resume`, `sse.reconnect_backoff`), WebSocket (`ws.pong_ok`, `ws.ticket_reuse`,
`ws.resubscribe`), downloads (`download.single_request`), editing cases or hunts
(`concurrency.if_match`, `concurrency.minimal_patch`), plus `estimate.rate`, `enrich.per_ip_storm`,
`import.checksum_mismatch`.

## How to verify

With the API up and the flow actually exercised in the UI:

```bash
cd ../backend
PYTHONPATH=src .venv/bin/python -m capture_api report          # add --all for the optional checks
PYTHONPATH=src .venv/bin/python -m capture_api doctor
```

No FAIL is the bar. Run it after every change to the data layer, not once at the end.

To reproduce the nasty cases without restarting the server:

```bash
PYTHONPATH=src .venv/bin/python -m capture_api admin expire-tokens --email ana@quillmere.example
PYTHONPATH=src .venv/bin/python -m capture_api admin revoke --email ana@quillmere.example
PYTHONPATH=src .venv/bin/python -m capture_api admin chaos --get-503-rate 0.3
PYTHONPATH=src .venv/bin/python -m capture_api admin reset
```

Chaos profiles for `serve --chaos`: `calm`, `flaky`, `storm`, `degraded-pcap`, `expiring-tokens`.
