# Roadmap: Capture

The order of work, from the foundation to the finished interface. Each numbered item is **one commit**
and is sized to be one `/spec` → `/plan` → `/implement` cycle. Before handing a commit over, run
`npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build`; add
`npm run test:e2e` when a spec covers the change, and `capture-api report` whenever the data layer
moved. The agent never commits — it hands back a verified tree and a message.

Stack: Next.js 16 App Router · React 19 · TypeScript · Tailwind v4 · TanStack Query v5 + Table · Radix.
Conventions live in `CLAUDE.md`; the rules the backend scores live in the `http-discipline` skill; the
call pattern lives in `api-layer`.

For each item: `/spec <item>` → `/plan specs/NNN-slug.md` → `/implement plans/NNN-slug.md`, then the
`code-reviewer` and `plan-verifier` agents.

---

## Phase 0: Foundation

Goal: every screen has its infrastructure ready, and nothing in the browser can reach the API directly.
**Done.** The next screen can fetch, format and fail without inventing anything of its own.

| #   | Commit  | What                                                                                                                                                                                                                                                                                                        | Tests                                                   |
| --- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| 0.1 | ✅ done | Toolchain, ESLint/Prettier, husky + commitlint, Vitest + Playwright, CI, Docker, `@api`/`@lib` aliases.                                                                                                                                                                                                     | smoke unit + e2e                                        |
| 0.2 | ✅ done | Server API layer: `rawFetch`, single-flight refresh, `callApi`, login/logout handlers, the `/api/capture` proxy, generated `schema.d.ts`.                                                                                                                                                                   | `query-retry`                                           |
| 0.3 | ✅ done | Query keys in one module (nested keys share their parent's prefix), `HttpError` carrying the API's stable code and any advertised wait, `fetchJson` as the browser's only reader, and response validation in the proxy.                                                                                     | keys, error mapping, fetch helper                       |
| 0.4 | ✅ done | `LoadingState`, `EmptyState`, `ErrorState`, `Skeleton` and minimal toasts. What a failure says, whether a retry is offered and how long to wait is decided once in `describeFailure`; every failure carries an id so a second refusal restarts the countdown. A dev-only gallery route feeds the e2e suite. | states, toasts, `describeFailure` branches, 6 e2e       |
| 0.5 | ✅ done | `@lib/format`: bytes (total plus both directions), durations (ms below a second), timestamps in UTC with the zone spelled out, endpoints, a shared empty marker, and `formatByColumnType` covering every column kind the API publishes. Ids are never parsed.                                               | boundaries, zeros, malformed input, locale independence |

---

## Phase 1: Sign in

Requirements: the token must never reach the browser; a HAR capture of the app must not contain it.

| #   | Commit  | What                                                                                                                                                                                                                                                                                                              |
| --- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1.1 | ✅ done | The sign-in form on React Hook Form + zod, validating against the API's own limits so a doomed attempt never spends one of the five it allows per minute. After a refusal the button counts down the stated wait, which here is a moment in time, not a number of seconds.                                        |
| 1.2 | ✅ done | Protected screens moved under a route group whose layout resolves the profile once per navigation. Only a missing session or a 401 redirects; an unreachable API reaches the error boundary. The destination travels through sign-in sanitized, the shell shows who is signed in, and signing out confirms first. |
| 1.3 | ✅ done | Every browser read reports through one seam, so a dead session is acted on once: cancel, clear, explain, leave — in that order, inside the five seconds the API allows. Transient failures change nothing.                                                                                                        |

- **Unit:** the login route handler maps 401/429 without leaking the upstream body; the logout path clears the store.
- **E2E:** a real sign-in with `ana@quillmere.example` / `demo-analyst` lands on `/search`; a wrong password shows the error; after sign-out, `/search` redirects to `/login`.
- **Scored:** `auth.bearer_from_browser`, `auth.logout_once`, `auth.refresh_single_flight`, `auth.refresh_reuse` (check with `admin expire-tokens`).

---

## Phase 2: Search

The main screen. A search is a server-side job: create it, follow it, read it page by page while it runs.

| #   | Commit  | What                                                                                                                                                                                                                                                                                    |
| --- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.1 | ✅ done | The capture points this account may read, with the lagging one marked, and a time window derived from the last traffic those points reported rather than from the clock — this capture ends in the past. The query lives in the address bar from here on.                               |
| 2.2 | ✅ done | A flat list of conditions joined by all-or-any, each negatable, built from the published fields and the comparisons each one declares; arity enforced before sending. Carried in the API's own `f=field:op:v1,v2` form. The catalogue is read once on the server and seeds the client.  |
| 2.3 | ✅ done | Matches and scan cost for a settled query, debounced and never polled, rounded so it reads as an estimate. The completeness rules are shared with the run control, so neither asks about a query the other would refuse.                                                                |
| 2.4 | ✅ done | `POST /v1/searches` with an `Idempotency-Key` derived from the query; an unchanged query re-uses the job it already started, the superseded one is `DELETE`d, and 429 `too_many_searches` waits out `Retry-After: 5`.                                                                   |
| 2.5 | ✅ done | `GET /v1/searches/{id}` polled with a backoff from half a second to five while the job runs, paused in the background, stopped the moment it ends; matched-so-far, scanned progress and cancel; a 410 reads as expired.                                                                 |
| 2.6 | ✅ done | A virtualized table over pages of 500, columns (order, visibility, widths, sortability) from `/v1/meta/columns` — including a column type the API document omits. Cursors go back verbatim; no cursor while running means caught up, so it reads the tail on a timer instead of paging. |
| 2.7 | ✅ done | Query, job and order all live in the address, so a result can be handed to someone else; the order is read from the server on a finished job, and a row opens `/sessions/{id}`. A job the server no longer has says so rather than failing.                                             |

- **Unit:** the filter builder produces a valid `FilterNode` for each operator and rejects bad arity; the cursor is never modified; `limit` is clamped.
- **E2E:** a search from the form reaches the results table; an empty result shows the empty state; cancelling stops the polling.
- **Scored:** `search.duplicate_jobs`, `search.abandoned`, `search.slots_exhausted`, `http.get_dedupe`, `http.invalid_cursor`, `http.limit_over_max`, `poll.health_interval`.

---

## Phase 3: Session

| #   | Commit  | What                                                                                                                                                                                                                                                                             |
| --- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 3.1 | ✅ done | `/sessions/{id}`: the summary header, and the transaction rendered from the protocol description — its labels, order and value kinds, every occurrence of a repeated field, and everything decoded but undescribed under its own path. A missing session says so.                |
| 3.2 | ✅ done | DNS written properly: the question and the response side by side, records beneath, flags in words, and the server's own reasons for the risk against the transaction. One reader reconciles both decoder generations; copyable values; the generic list stays.                   |
| 3.3 | ✅ done | A mirrored byte/packet timeline over the session's own lifetime: widths derived from its duration and always inside the range the server accepts, omitted buckets drawn as gaps, the numbers behind the picture readable by keyboard, and a session too short to plot saying so. |
| 3.4 | ✅ done | What the server relates to this session, within one of the three windows it accepts: a compact line per session linking to it, more pages read with the server's own marker, and no claim about why they are related.                                                            |

- **Unit:** the schema-driven renderer maps every `FieldType` and survives an unknown one; ids stay strings.
- **E2E:** opening a row from the results shows the session; a missing id shows the not-found state.

---

## Phase 4: Resilience and polish

| #   | Commit  | What                                                                                                                                                                                                                                                                                           |
| --- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 4.1 | ✅ done | A refused read costs the part that needed it, not the screen: the capture-point list, the session, the timeline and the neighbours each report in place, and a retry says it is retrying and re-arms after a dropped connection. Expiring tokens stay invisible.                               |
| 4.2 | ✅ done | Withheld values read as withheld instead of printing the server's marker; the list behind a closed-field condition reports its own failure, offers a retry and still lets the value be typed; and the server's own degraded parts are quoted once above every screen, through a rationed read. |
| 4.3 | ✅ done | Results are a `grid` with one tab stop and arrow/Home/End movement; focus follows the roving index only when a key moved it. `e2e/a11y.spec.ts` runs axe-core at WCAG 2.1 AA over the three screens and fails on any violation; it found an unnamed progress bar, now named.                   |
| 4.4 | ✅ done | The visible columns and the flattened pages are stable across renders, and rows and header cells are memoised. Nothing measured as slow, so no profiler number is claimed — the memoisation is a correctness fix, not a win.                                                                   |

- **Gate:** run after `capture-api admin reset`, because the report accumulates across runs.
  `calm` — 0 fail ✅. `expiring-tokens` — 0 fail ✅. `doctor` — clean ✅. `storm` — 0 fail ✅,
  three consecutive runs.
  `http.retry_after_violations` took three attempts. The first two were per-caller: the poll
  interval ignored a `Retry-After` that arrived between ticks (`pollDelay`), and `holdRead`
  remembered answers but not refusals (the field catalogue is rationed by its own handler so the
  server render and the browser share one memory of it). **The third cause was `/v1/me`** — the
  guard's profile read, not the search read, which is why looking at the search code never found
  it: `shareProfileRead` shares the read in flight and keeps nothing, so a refusal was forgotten
  the instant it was thrown. Reproduced deliberately by `e2e/retry-after-gate.ts`
  (`npm run gate:retry-after`), a traffic generator that asserts nothing and so survives long
  enough to produce the traffic the specs never could: 12 violations before, 0 after.
  Fixed at the seam rather than at a third caller — `callApi` remembers a refusal against its route
  template and waits out the remainder before the next call on that template, which is how the API
  actually keys its windows (`src/lib/api/advertised-delay.ts`).

---

## Phase 5: The investigation and the write-up

| #   | Commit  | What                                                                                                                                                                                                                                                                                                                             |
| --- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 5.1 | ✅ done | `ws-hb-009.quillmere.example` (10.20.40.18) at harbor-branch, starting 2025-10-25 03:11:38 UTC with the first lookup of `telemetry.static-assets-cdn.test`. Written up in the README with two session links and a re-runnable query, the scanner and the NXDOMAIN bursts ruled out, and the estimate's any-join defect recorded. |
| 5.2 | ✅ done | The project README: how to run it, the three screens, how it is arranged, what is done and what is not with reasons, the three kinds of test with their commands, the four defects found in what was given, and an AI disclosure with a line left for the author.                                                                |

---

## Phase 6: Optional, only if time is left

One finished thing beats five started ones. Each item brings its own scored checks.

| #   | Commit                               | What                                                                                         | Scored                                                   |
| --- | ------------------------------------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| 6.1 | `feat(live): add the detection feed` | SSE over `/v1/stream/detections` with a resume point and backoff, one stream at a time.      | `sse.double_open`, `sse.resume`, `sse.reconnect_backoff` |
| 6.2 | `feat(live): add the websocket feed` | `/v1/live/tickets` + WS: a ticket used once, pings answered, re-subscribe after a reconnect. | `ws.pong_ok`, `ws.ticket_reuse`, `ws.resubscribe`        |
| 6.3 | `feat(session): add downloads`       | PCAP and carved files, one request per file, streamed through a route handler.               | `download.single_request`                                |
| 6.4 | `feat(hunts): add saved queries`     | `/v1/hunts` CRUD with `If-Match` and minimal `PATCH` bodies.                                 | `concurrency.if_match`, `concurrency.minimal_patch`      |
| 6.5 | `feat(enrich): annotate addresses`   | Batched `/v1/enrich/ips`, never a storm of single lookups.                                   | `enrich.per_ip_storm`                                    |

---

## Test inventory (planned)

- **Unit (Vitest):** retry policy and `Retry-After` parsing (done), query keys, formatters, the filter builder, cursor handling, the schema-driven renderer, route-handler error mapping.
- **E2E (Playwright):** sign in / sign out, search → results → session, the empty state, cancelling a search, a dead session redirecting to `/login`.
- **Backend verdict:** `capture-api report` after every phase that touches the data layer.

## Open questions (all settled; kept for the record)

Answered in the order they came up: a flat condition list (2.2), our own windowing with TanStack
Virtual (2.6), DNS as the first-class protocol (3.2), the flow timeline and related sessions kept in
phase 3 rather than moved to 6 (3.3/3.4), and no separate affordances for the observer beyond marking
a withheld value as withheld (1.2). The questions as they were first written:

1. **Phase 2.2** — how much of the condition builder do we want: flat `all` conditions only, or full `any`/`not` nesting? Flat is faster and covers the task; nesting is the honest read of `/v1/meta/fields`.
2. **Phase 2.6** — do we window the table ourselves (TanStack Virtual) or cap the page size? Windowing is the right answer at a hundred thousand sessions, and it is extra work.
3. **Phase 3.2** — which protocol gets the first-class view? DNS is the smallest to do well; HTTP shows more.
4. **Phase 3.3 / 3.4** — flow and related sessions are not required by the task. Keep them in Phase 3, or move them to Phase 6?
5. **Phase 1.2** — does the observer account need its own visible affordances (hidden fields explained), or is it enough that restricted data simply does not render?
