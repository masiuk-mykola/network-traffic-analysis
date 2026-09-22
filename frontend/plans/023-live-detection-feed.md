# 023 — Plan: the live detection feed

Spec: [`specs/023-live-detection-feed.md`](../specs/023-live-detection-feed.md). Read it first — all
five open questions are answered there, and the decisions below only make sense beside them.

## What the server actually does

`backend/src/capture_api/realtime/sse.py`, read rather than assumed, because every design choice
here follows from it:

- the stream opens with a `: open last_seq=<n>` comment and `retry: 3000`; live events carry
  `id: <seq>` and `event: detection`;
- a resume point arrives as `Last-Event-ID` (which wins) or a query parameter, and replays a ring of
  the **last 1,000 detections**; a point older than the ring yields one `reset` event carrying
  `oldest_seq` and `last_seq` instead of a replay;
- the stream ends **three ways**: a `reauth` event when the access token it opened with expires,
  silence when the token family is revoked, and silence on rotation — **300 s calm, 60 s flaky,
  20 s storm** (`platform/chaos.py`). Rotation is the normal case, not the exception;
- `/v1/stream/` is **exempt from chaos** (`chaos.py:24-32`), so the stream itself is never refused
  with a `Retry-After`. `/v1/detections`, which the backfill uses, is not exempt and goes through
  the seam that already handles that.

What is graded (`api/observer.py:332-375`, `SSE_MIN_GAP_S = 1.0`), **per token family**:

| Check                   | Rule                                                       |
| ----------------------- | ---------------------------------------------------------- |
| `sse.double_open`       | no two opens within 1 s                                    |
| `sse.resume`            | ≥ 95 % of re-opens carry a resume point (< 80 % is a FAIL) |
| `sse.reconnect_backoff` | no open within 1 s of a close                              |

**Per token family** is the whole design. Two tabs are one family, so a per-tab stream is an instant
`sse.double_open` failure. The connection therefore cannot live in the browser: it lives once, on
our server, keyed by session — the same shape as `@api/advertised-delay` and the rationed health
read, for the same reason.

## Shape

```
browser tab ─┐
browser tab ─┼─→ /api/detections/stream  (our SSE, one per tab, no Authorization)
browser tab ─┘            │
                          └─→ one upstream stream per session ──→ /v1/stream/detections
                                 remembers last seq, reconnects with backoff
```

Our own route re-emitting to each tab is free: the browser reconnecting to _us_ is not a request the
API ever sees. Only the upstream connection is graded, and there is exactly one.

## Files to touch

| File                                          | What                                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------------- |
| `src/lib/api/sse.ts` (+ test)                 | **new** — parse an SSE byte stream into frames. Pure, so it is unit-tested            |
| `src/lib/api/stream.ts`                       | **new** — one raw authorized streaming GET; no timeout, no JSON, no retry             |
| `src/lib/detections/upstream.ts` (+ test)     | **new** — the single stream per session: subscribers, resume point, reconnect, grace  |
| `src/lib/detections/reconnect.ts` (+ test)    | **new** — the backoff policy, on its own so it can be tested without a socket         |
| `src/app/api/detections/stream/route.ts`      | **new** — the browser's SSE endpoint; subscribes, re-emits, never forwards a token    |
| `src/app/(app)/detections/page.tsx`           | **new** — the screen; server component, reads the backfill so the browser inherits it |
| `src/app/(app)/detections/detection-feed.tsx` | **new** — `'use client'` leaf: the list, the connection's condition, the three states |
| `src/lib/detections/use-detections.ts`        | **new** — the hook: backfill seed + our stream, merged and de-duplicated by `seq`     |
| `src/lib/api/keys.ts`                         | the backfill's cache identity                                                         |
| `src/lib/api/response-schemas.ts`             | validate the backfill through the proxy, as every other read is                       |
| `src/lib/routes.ts`                           | the screen's address                                                                  |
| `src/components/app-header.tsx`               | one nav item beside Search                                                            |
| `src/app/api/auth/logout/route.ts`            | stop the stream before the session is dropped                                         |
| `e2e/detections.spec.ts`                      | **new** — the screen, the link to a session, the two-tab case                         |
| `README.md`, `plans/000-roadmap.md`           | 6.1 marked done, and what the three checks now report                                 |

Nothing under `src/app/(app)/search/**` or `src/app/(app)/sessions/**` is edited — the feed is added
beside the finished screens, per the spec's non-goals.

## Steps

### 1. The SSE parser, on its own (TDD)

`src/lib/api/sse.ts`: bytes → frames. This is the deterministic core and the easiest thing to get
subtly wrong, so it is written test-first against the shapes the server actually sends: a comment
line (`: open last_seq=12`), a `retry:`, a frame with `id`/`event`/`data`, multi-line `data`, a
frame split across chunk boundaries, `\r\n` as well as `\n`, and a trailing partial frame at
end-of-stream. Negative cases are the point here, not decoration.

### 2. One raw streaming call

`src/lib/api/stream.ts`: `rawStream()`, beside `rawFetch` rather than inside it — `rawFetch` reads a
body to completion and applies a 15 s timeout, both of which are exactly wrong for a stream. It adds
the bearer, sets `accept: text/event-stream`, takes an abort signal and **no timeout**, and returns
the response so the caller owns the body. A non-200 becomes the same `ApiError` as everywhere else.

It deliberately does not go through `callApi`: a stream is not a request that can be replayed after
a refresh, and the reconnect policy in step 3 is where a dead token is handled instead.

### 3. The backoff policy, on its own (TDD)

`src/lib/detections/reconnect.ts`. Small and pure, so the graded rule is provable without a socket:

- never sooner than **1 s** after an ending — the server's own threshold, with room above it;
- the server's `retry: 3000` hint is the floor in the ordinary case;
- a failure to open lengthens it, doubling to a ceiling; a successful open resets it;
- `reauth` and rotation are ordinary endings, not failures, so they take the floor, not the ceiling.

### 4. One upstream stream per session (TDD for the bookkeeping)

`src/lib/detections/upstream.ts`, `server-only`, on a `globalThis` map keyed by session id — the
shape `@api/hold` and `@api/advertised-delay` already established, and for the same reason: a module
reload must not lose it, and the API grades per family.

- `subscribe(sessionId, onEvent)` → an unsubscribe. The first subscriber opens the stream; later
  ones attach to the one already running.
- The last subscriber leaving does **not** close it. A timer closes it after a grace period (spec
  answer 4), and a subscriber arriving inside that window cancels the timer — a tab hidden and shown
  again must not produce a close/open pair.
- The resume point is the highest `seq` seen, held per session and **outliving the connection**, so
  every re-open carries `Last-Event-ID`. That is `sse.resume` in one line.
- Endings are told apart: a `reauth` event means fetch a fresh token and re-open at the floor delay;
  a silent end is rotation and is treated the same; a `SessionGone` or a 401 stops for good and
  clears the entry, so nothing reconnects into a revoked family.
- A `reset` frame is passed through as an ending to explain, not an error, and the resume point is
  replaced with the `last_seq` the server named.

The unit tests drive this with a fake stream source: subscriber counting, the grace timer, the
resume point surviving a re-open, `reauth` refreshing once, and a stop that stays stopped.

### 5. The browser's own endpoint

`src/app/api/detections/stream/route.ts`: a `ReadableStream` response with
`content-type: text/event-stream` and `cache-control: no-store`. It requires a session like every
other handler, subscribes to the upstream, and writes three kinds of frame to its one tab —
`detection`, `reset`, and a `status` frame carrying live / reconnecting / stopped. It unsubscribes
on the request's abort signal. No `Authorization` is ever constructed here; the token stays in the
upstream module behind `server-only`.

### 6. The backfill, as an ordinary read

AC-2 wants what the server still holds on opening, and the stream alone only replays on a _resume_.
So the newest page of detections is read the way every other read is read — through the existing
proxy, with a key in `@api/keys` and a generated schema in `@api/response-schemas`. The screen reads
it on the server so the browser inherits it instead of asking again, exactly as the search screen
does with a job. `limit` stays within what the server accepts.

### 7. The screen

`src/app/(app)/detections/page.tsx` (server) + `detection-feed.tsx` (`'use client'` leaf) +
`use-detections.ts`. The hook seeds from the backfill, opens our endpoint, merges by `seq`,
de-duplicates, keeps newest first and caps the list at the ring's size so it cannot grow without
bound. Session ids are strings throughout and nothing parses one. Values go through `@lib/format`.

All three states ship in this step, from `@/components/states`: the backfill's loading state, an
empty feed that reads as quiet rather than broken, and a failure that reports in place with a retry
and leaves the rest of the screen usable. The connection's condition is a separate, quieter line —
a failing stream must not look like a failing screen. The list is a polite live region, announced
by arrival count rather than by reading each row aloud.

### 8. Sign-out

The logout handler stops the stream **before** `dropSession`, so nothing is in flight when the
family is revoked (`auth.logout_once` allows nothing later than 5 s after). The upstream's own
`SessionGone` path is the belt to that braces: a stream that finds its session gone stops and does
not reconnect.

### 9. Verify, then document

`report --all` under `calm`, `storm` (where rotation every 20 s exercises the reconnect hardest) and
`expiring-tokens` (which is what makes `reauth` happen at all), three runs each. Then `README.md`
and `plans/000-roadmap.md`, and the PIR that
`.claude/rules/common/06-post-implementation-review.md` requires.

## Risks

- **A per-tab stream would fail `sse.double_open` instantly.** This is the whole reason the
  connection lives on the server. Proven by the two-tab e2e case and by the report.
- **A dev server reload orphans the upstream.** The map is on `globalThis`, but a hot reload can
  still leave a stream without its owner. Bounded by rotation — the server ends it within 20–300 s
  either way. Worth knowing when reading the report after a long dev session.
- **Per-process, like every other memory here.** Two app instances are two streams, which the API
  would read as one family opening twice. Accepted, stated in the README, same limitation already
  recorded for advertised delays.
- **A long-lived fetch with no timeout.** Deliberate, and the reason `rawStream` is separate from
  `rawFetch`; the abort signal is the only way it ends early, and every path that stops the stream
  aborts it.
- **`reauth` storms.** A refresh per re-open would be one thing; a refresh per _failed_ re-open
  would be a loop. The token is taken from the existing single-flight store, and the backoff applies
  to reauth-triggered opens exactly as to any other.
- **The grace period holds a connection nobody is reading.** That is the trade the spec chose: one
  idle connection is cheaper than a close/open pair each time a tab is hidden.
- **Three checks that currently report nothing become three that can fail.** The honest cost of
  taking the feature on, and the reason step 9 runs the report under all three profiles rather than
  once under `calm`.

## Verification

| Acceptance criterion                             | Proved by                                                                                                             |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| AC-1 — detections arrive without reload          | `e2e/detections.spec.ts`: the feed grows while the page is untouched                                                  |
| AC-2 — what the server holds, on opening         | e2e: rows present on first paint; plus the server-read backfill inherited by the browser                              |
| AC-3 — a detection leads to its session          | e2e: click a row, the session screen opens with that id                                                               |
| AC-4 — resume loses and repeats nothing          | Unit over `upstream`: the resume point survives a re-open; e2e across a forced rotation                               |
| AC-5 — a refused resume point is explained       | Unit: a `reset` frame becomes an ending to explain and replaces the resume point                                      |
| AC-6 — two tabs, one stream                      | e2e with two contexts; confirmed by `sse.double_open` in the report                                                   |
| AC-7 — resume point and backoff on re-open       | Unit over `reconnect` (never under 1 s, floor at the server's hint); `sse.resume` + `sse.reconnect_backoff`           |
| AC-8 — an expiring token does not stop it        | `report` under `expiring-tokens` with the feed open; unit for the `reauth` path                                       |
| AC-9 — nothing survives sign-out                 | e2e: sign out with the feed open, then `auth.logout_once` in the report                                               |
| AC-10 — no token in the browser                  | e2e: no `Authorization` on any browser request; the stream route constructs none                                      |
| AC-11 — the three checks pass, nothing regresses | `report --all` under `calm`, `storm`, `expiring-tokens`, three runs each; `doctor`                                    |
| AC-12 — the write-up matches                     | `README.md` and `plans/000-roadmap.md` diffs read against the report output                                           |
| Nothing else regressed                           | `npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build`, then `npm run test:e2e` |
| Coverage threshold held                          | `npm run test:coverage` — the new logic is all under `src/lib`, which CI holds to a threshold                         |

Per `.claude/rules/common/07-git-boundaries.md` the work ends with a verified tree and commit
messages. The human commits.

---

## Post-implementation review — 2026-09-22

Per `.claude/rules/common/06-post-implementation-review.md`, written before hand-off.

**What the change actually did.** AC-1 through AC-11 are satisfied; the evidence is in the
Verification table above, each row now backed by a passing test, a driven flow or a report line. The
numbers that matter: three consecutive `storm` runs with `sse.double_open`, `sse.reconnect_backoff`
and `sse.resume` (100 %) all passing and 0 fail; the full suite at 76/76 and `report` at 196 pass /
0 warn / 0 fail after it; the 022 gate still clean, so the retry-after work did not regress.

**What broke.** Two real defects, both found by the report rather than by a test.

1. `GET /v1/detections` violated `http.retry_after_violations` — 0.92 s after a 503 asking for 1 s.
   The advertised-delay seam from 022 could not prevent it, and that is the interesting part: under
   storm the API holds a request for up to 1.5 s, so a second mount issued its seed read _before_
   the first one's refusal came back. A memory of a delay is useless against a read already in
   flight. The fix was to stop making the second read at all — the seed is rationed by its own
   handler and shares the read in flight, the pattern `/v1/meta/fields` and `/v1/health` already
   use. I confirmed it was not a dev-server artefact by reproducing it against a production build
   first.
2. The long rotation spec destabilised the spec that ran after it: session-expiry failed roughly one
   run in three with it present, and 9/9 passed without it. It moved out of the suite and into a
   gate.

**What surprised us.** Three things.

- The server reads its rotation interval **when the stream is built** (`self._rotate_s`), so a storm
  switched on after the stream was already open leaves it on calm's 300 s and it never rotates. My
  first gate run therefore reported `sse.resume` as n/a and looked like a passing feature; it was
  measuring nothing. The check being `n/a` rather than `pass` is what gave it away.
- `sse.resume` needs a family that re-opened, so it is structurally invisible to a suite where every
  spec signs in fresh. Two of the three checks can pass while the third has no data at all.
- The plan assumed the risk was holding a token in the browser or opening twice per tab. Both were
  handled by the design on the first try. The actual cost was everywhere else: chunk boundaries,
  in-flight duplicate reads, and test isolation.

**What the rulesets should learn.** One proposal, for `.claude/rules/common/05-definition-of-done.md`,
under **Behavior**: _when an acceptance criterion is proved by an external grader, record the check's
value, not just its status — a check reporting "not applicable" is not a check that passed._ Both of
this run's near-misses (a feature that looked done with `sse.resume` n/a, and 022's storm result
before it) would have been caught at the gate by that one line.

No other ruleset updates.

**Open follow-ups.**

- Per-process, like every other memory here: two app instances are two streams, which the API would
  read as one family opening twice. Stated in the README; it becomes real work only behind more than
  one instance.
- The seed is held for five seconds. That is enough to collapse a burst of mounts and short enough
  that the list is never stale in practice, because the stream keeps it live — but the number was
  chosen by reasoning, not measured.
- `e2e/detection-resume-gate.ts` and `e2e/retry-after-gate.ts` both take the account and must run
  alone. Nothing mechanically prevents someone running one beside `npm run test:e2e`.
- The feed offers no filter by capture point and announces nothing outside its own screen, both
  settled as out of scope in the spec. If a reader is ever expected to notice a detection while on
  another screen, that decision reopens.
