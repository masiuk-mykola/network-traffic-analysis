# 022 — Plan: honour every advertised delay, whoever asks next

Spec: [`specs/022-advertised-delay-discipline.md`](../specs/022-advertised-delay-discipline.md).
Read this before implementing. Open questions 1, 2 and 4 are answered in the spec; question 3 —
which caller actually causes the surviving violation — is answered by step 1 of this plan, and
**nothing in steps 3 onward is written before step 1 produces evidence**
(`.claude/skills/systematic-debugging`).

## What the server scores, exactly

`backend/src/capture_api/api/observer.py:227-246`. Worth restating, because the fix follows from it
and the previous two attempts were aimed at a narrower target:

- a `429` or `503` carrying `Retry-After` opens a window until `t + retry_after_s`;
- the window is keyed by **route template** (`/v1/searches/{search_id}`), per **token family** —
  not by the concrete id, not by path+query;
- **any** later request on that template inside the window is an offender, of any method and any
  status — a `DELETE` offends as much as a `GET`;
- strict `<`, no tolerance. `storm` advertises `randint(1, 3)` whole seconds
  (`backend/src/capture_api/platform/chaos.py:82-92, 328-356`), and rolls faults on `GET` only;
  `/v1/health` and `/v1/auth/*` are exempt.

The consequence that decides the design: the unit that must remember a delay is **the route
template, on the server, for every outbound call** — not any one hook, screen or handler. Today
`src/lib/api/server.ts:8` (`callApi`) is already the single seam every server-side call passes
through, for the SSR reads, the read proxy, the search write handlers and the rationed handlers
alike. Nothing else needs to know.

## Files to touch

| File                                  | What changes                                                                                     |
| ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `scripts/sync-api-schema.mjs`         | a third generation step, writing the document's path templates to a runtime module               |
| `src/lib/api/generated/routes.gen.ts` | **new, generated** — the route templates as a runtime array                                      |
| `src/lib/api/route-template.ts`       | **new** — match a concrete `/v1/...` path to its template; unknown paths fall back to themselves |
| `src/lib/api/advertised-delay.ts`     | **new** — remember a delay per session and template; await what remains of it                    |
| `src/lib/api/server.ts`               | `callApi` waits out a remembered delay before sending, and records a refusal that names one      |
| `src/lib/search/use-results.ts`       | `nextPollDelay` → `pollDelay`, reading the advertised wait off the query state                   |
| `src/lib/api/hold.ts`                 | the refusal memory moves out; `holdRead` keeps only the answer and the read in flight            |
| `e2e/retry-after-gate.ts`             | **new, not a spec** — the traffic generator, run by hand                                         |
| `package.json`                        | a script that runs the generator                                                                 |
| `README.md`, `plans/000-roadmap.md`   | the `storm` result, the third cause, the gate command                                            |

Plus tests beside each new module, and `src/lib/api/hold.test.ts` adjusted where the refusal
behaviour moves.

## Steps

### 1. Reproduce, before anything is changed

1.1 Bring the API up and reset it, so the report counts only this run:

```bash
docker compose up -d --wait simulator
cd backend && uv run capture-api admin reset
```

1.2 Write the traffic generator at `e2e/retry-after-gate.ts` — a Playwright script, **not** a spec,
so nothing aborts on the first refused read. It signs in with the fixture account, opens `/search`,
starts a search, navigates away and back (which re-renders on the server), changes the order,
cancels, and repeats for a fixed number of rounds. Reuse `e2e/search-flow.ts:12-41` (`setChaos`,
`calmDown`, the slot bookkeeping) rather than re-writing chaos switching; it already restores
`calm`.

1.3 Instrument the seam. In `src/lib/api/server.ts`, temporarily log method, path, a monotonic
timestamp, the response status and any `Retry-After`, plus a caller label threaded through
`ApiRequest`. This is the evidence, and it comes out again in step 6.

1.4 Run it twice: once at storm's own rates, once with refusals forced —

```bash
uv run capture-api admin chaos calm --get-503-rate 1.0 --drop-rate 0.0
uv run capture-api admin chaos storm
uv run capture-api report --all --json --since 600
```

The report's evidence names the offender directly:
`retried {gap}s after a {status} asking for {n}s`, with the timestamp and the path — capped at five
per check per family, which is why each run is short and scoped with `--since`.

**Exit criterion:** a matched pair in our own log — A refused with `Retry-After: N`, B on the same
template sent less than N later — with B's caller named. Record it in the spec under question 3.

### 2. A failing test, before the fix

Unit, at `src/lib/api/advertised-delay.test.ts`: a refusal on one path makes the next call to a
_different_ concrete path of the same template wait out the remainder, and a refusal naming nothing
changes nothing. Written to fail first (`.claude/skills/tdd`).

### 3. Generate the route templates

`scripts/sync-api-schema.mjs:25-35` already runs two generators over the document, from the live API
when it is up and from `../backend/openapi.json` otherwise. Add a third step that writes
`src/lib/api/generated/routes.gen.ts`:

```ts
export const ROUTE_TEMPLATES = ['/v1/searches/{search_id}', ...] as const
```

Taking the templates from the contract rather than writing a matcher by hand keeps the rule of this
repo — the table is built from what the server publishes — and means a new endpoint is covered the
day it appears. `src/lib/api/route-template.ts` matches a concrete path segment by segment against
that list, longest literal prefix first, and returns the path unchanged when nothing matches, so an
unknown path is simply its own window.

### 4. One memory of a delay, at the one seam

`src/lib/api/advertised-delay.ts`, in the shape `src/lib/api/hold.ts` already established — a
`globalThis` map so a module reload does not lose it:

- `rememberDelay(sessionId, template, retryAfterMs)`;
- `awaitDelay(sessionId, template, signal)` — resolves at once when there is nothing to wait for,
  otherwise after the remainder, and rejects if the caller's signal aborts first.

Keyed by session id as well as template, because the server scores per token family and because two
accounts against one dev server must not delay each other.

`callApi` (`src/lib/api/server.ts:8-21`) then does three things it does not do today: await the
delay before `rawFetch`, record a refusal that named one, and leave everything else alone. The 401
refresh-and-replay path is inside the same try, so the replay is covered too.

This is where the design pays for itself: the SSR read in `src/app/(app)/search/page.tsx:49`, the
read proxy at `src/app/api/capture/[...path]/route.ts`, the `DELETE` in
`src/app/api/searches/[id]/route.ts:17` and the rationed handler at
`src/app/api/capture/fields/route.ts` all call `callApi`, so all four are covered by one change and
none of them learns a new rule.

**Waiting, not refusing**, per the spec's answer to question 2: a cancel clicked inside a delay is
held for at most three seconds and then sent. The screens already show a pending write, so nothing
new is needed in the interface; step 7 confirms that by eye.

### 5. Retire the duplicated memory

With `callApi` holding delays, `holdRead`'s `refused` slot (`src/lib/api/hold.ts:19,33-37,44-48`) is
a second memory of the same fact, keyed differently. Remove it and its two tests
(`src/lib/api/hold.test.ts:45-66`), leaving `holdRead` to do the one thing its name says: hold an
answer and share a read in flight. Two memories of one delay is how the previous two fixes were
arrived at, and is the thing to stop repeating.

Keep `src/app/(app)/search/page.tsx:49`'s `holdRead(..., 0, ...)` call only if step 1's evidence
shows it still earns its place; with the delay handled underneath, a zero window does nothing but
share an in-flight read, which is worth keeping in its own right.

### 6. The results poller, on its own merits

`src/lib/search/use-results.ts:49-56` computes its interval from `nextPollDelay(pages.length)` and
knows nothing of an advertised wait, unlike `src/lib/search/use-search.ts:41-51`. Swap in
`pollDelay` with the wait read off the query state the same way. `/v1/searches/{id}/results` is its
own template and its own window, so this is a real defect whichever hypothesis step 1 confirms — but
it is a _browser-side_ improvement over a server-side guarantee, so it is a second commit, not part
of the first.

Then remove the instrumentation from step 1.3 and `grep` the diff to prove it is gone.

### 7. Verify, then document

Run the gate three times (it is intermittent; one clean run proves nothing), then update
`README.md:150-168` and `plans/000-roadmap.md:92-99` with what the report now says and what the
third cause was. Write the PIR required by `.claude/rules/common/06-post-implementation-review.md`.

## Risks

- **Holding a browser request open.** A route handler that waits up to three seconds before calling
  the API lengthens a request the browser is already waiting on. Bounded by what the server asked
  for, and the alternative is a scored violation. The abort signal is honoured so a cancelled query
  does not hold a handler.
- **Double waiting.** React Query's `retryDelay` (`src/lib/query-retry.ts:16-22`) already waits out
  `Retry-After` in the browser, and now the server waits too. The result is a later request, never
  an earlier one — harmless for the check, but it must not be mistaken for a bug when timings move.
- **A delay remembered too widely.** The template matcher must not collapse two different endpoints
  into one window (`/v1/searches/{id}` and `/v1/searches/{id}/results` are separate). Covered by a
  unit test over every templated path in the document.
- **Per-process memory.** Accepted in the spec. A restart forgets; two server instances do not
  share. Worth one line in the README rather than a pretence of durability.
- **The single-flight refresh.** `refreshAfterUnauthorized` must not be delayed into a window that
  belongs to a different template; `/v1/auth/*` is exempt from chaos and the delay is keyed by
  template, so it is not — but the test for it is cheap and goes in.
- **Tests that now take real time.** `awaitDelay` in a unit test uses fake timers; a test that
  actually sleeps three seconds is a test that will be deleted by the next person in a hurry.
- **The e2e suite's shared account.** The generator takes search slots and signs out; it runs alone,
  never beside `npm run test:e2e`, and hands slots back through `e2e/search-flow.ts`.

## Verification

| Acceptance criterion                                                    | Proved by                                                                                                             |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| AC-1 — refused render is not followed by a browser ask inside the delay | Unit over `callApi` with a stubbed `rawFetch`; plus the step-1 log showing the pair no longer appears                 |
| AC-2 — refused browser read is not followed by a render ask             | Same unit, the two callers reversed                                                                                   |
| AC-3 — cancel and supersede respect the window                          | Unit over `advertised-delay` proving a non-GET on the template waits; the generator exercises both                    |
| AC-4 — the results list is not re-asked inside its own delay            | `src/lib/search/use-results.test.tsx` with a refusal carrying `Retry-After`                                           |
| AC-5 — forced-refusal run is clean                                      | `admin chaos calm --get-503-rate 1.0 --drop-rate 0.0`, the generator, then `capture-api report`                       |
| AC-6 — three storm runs clean                                           | `admin reset` + generator + `report`, three times, under `storm`                                                      |
| AC-7 — other profiles intact                                            | `report` under `calm` and `expiring-tokens`; `capture-api doctor`                                                     |
| AC-8 — no advertised delay changes nothing                              | Unit: a refusal without `Retry-After` sends the next call immediately                                                 |
| AC-9 — the write-up matches the report                                  | `README.md` and `plans/000-roadmap.md` diffs, read against the report output                                          |
| Nothing else regressed                                                  | `npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build`, then `npm run test:e2e` |
| Coverage threshold held                                                 | `npm run test:coverage` — the new modules are all under `src/lib`, which CI holds to a threshold                      |

Per `.claude/rules/common/07-git-boundaries.md` the work ends with a verified tree and a commit
message. The human commits.

---

## Post-implementation review — 2026-09-22

Written per `.claude/rules/common/06-post-implementation-review.md`, before the hand-off rather
than after a merge: this is the last graded check, so there is no later feedback cycle to wait for.

**What the change actually did.** AC-1 through AC-8 are satisfied (see the plan's Verification
table for the evidence against each). The measurable one: the same generator run that produced
**12** `http.retry_after_violations` before the fix produces **0** after it, and three consecutive
`storm` runs report none. The full e2e suite (71 specs) and `report` under `calm` — 178 pass, 0 warn,
0 fail — show nothing regressed. AC-9 is the README and roadmap rewrite, checked against that
output rather than against the old text.

**What broke.** Nothing regressed. One thing in the plan was wrong on contact: step 1's generator,
written to refuse every read from the start, produced no search traffic at all, because a screen
whose every read is refused never offers a capture point to tick. It started the job under `calm`
and turned the refusals on afterwards instead — a two-line change, but the first run was wasted.

**What surprised us.** The offender was `/v1/me`, which nobody had suspected: two previous fixes,
the README, the roadmap and the spec's own framing all named "the search status read". The
inspection hypothesis written into this plan (`holdRead` keyed by concrete id rather than by
template) was _plausible, related and not the cause_ — it is a real second memory of the same fact,
and removing it was right, but it was never what failed. Following the plan's own rule — reproduce
before writing anything — is the only reason the fix landed at the seam rather than becoming a
third per-caller patch on the wrong caller.

A second surprise, which is the stronger argument for the design: the search read _did_ honour the
delay, and still offended, by 1.83 s of a 2 s window. `pollDelay` measures from when the browser
received the refusal; the server measures from when it received the request. The round trip through
our own proxy is the difference. A browser-side wait cannot close that gap on its own.

**What the rulesets should learn.** One proposal, for
`.claude/rules/common/01-research-protocol.md`, Pass 2 (Blocker refinement): _when a blocker
concerns behaviour graded by an external system, read that system's own rule as evidence before
reasoning about the client — a check's name is not its definition._ Two attempts at this check were
aimed at "the search status read" because that is what the check's evidence string happened to
print; ten lines of `observer.py` said it was keyed by route template, per family, closed by any
method, and that single fact is what made the design obvious.

No other ruleset updates.

**Open follow-ups.**

- The delay memory is per process (`globalThis`), like `holdRead`. A restart forgets it and two app
  instances do not share one. Accepted in the spec, stated in the README; it becomes real work only
  if this is ever run behind more than one instance.
- `shareProfileRead` still keeps nothing after it settles. That is now harmless — the seam holds the
  delay underneath — but the guard reads `/v1/me` on every navigation, which `http.get_dedupe`
  reports at 2 of its allowed 2 under load. Not a failure; worth watching if another per-navigation
  read is ever added.
- `e2e/retry-after-gate.ts` takes the account's search slots and must run alone. It is out of the
  suite by filename and behind its own config, but nothing mechanically prevents someone running
  both at once.
