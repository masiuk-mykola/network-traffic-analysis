# 018 — Survive an unreliable server (implementation plan)

Read this before implementing. The spec is `specs/018-survive-chaos.md`.

## Decisions taken (the spec's open questions, answered)

- The server's own component health (its "index is rebuilding") is **out of scope** here; it is a
  status surface, and belongs with the rest of the states in 4.2.
- Recovery keeps **the server's delays**, with no budget of our own — but the attempt becomes
  **visible**: while a read is being re-attempted, the part that failed says so instead of sitting
  silent.

## What the server gives us to test with (probed 2026-09-21)

The chaos profile can be set at runtime, and — the useful part — **overridden per rate**:

```
PUT /v1/__admin/chaos   {"profile":"calm","overrides":{"get_503_rate":1.0}}
```

So a failure path can be driven **deterministically** (every read refused) rather than statistically,
which is the only way an end-to-end test of this is not a coin toss. `/v1/health` and the auth paths
are exempt from chaos, so sign-in still works with every read refused. Restoring is the same call
with empty overrides.

The two profiles in the spec, in numbers: `storm` is `get_503_rate 0.20`, `drop_rate 0.05`, latency
200–1500 ms, search refusals 10 % before and after commit and 1 % failing mid-scan;
`expiring-tokens` is an access token that lives 15 s.

## Where it breaks today (observed, not assumed)

| Screen               | Under a refused read                                                                                                                                                                                                 |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/search`            | `query-form.tsx` returns `<ErrorState>` **instead of the whole form** when the capture-point read fails, and an `EmptyState` when it comes back empty. The window, the conditions and the run control all disappear. |
| `/sessions/[id]`     | `session-view.tsx` returns `<ErrorState>` for the whole screen, so even the way back is gone. Its timeline and neighbours already own their failures — the summary does not.                                         |
| Any retry            | `ErrorState` cannot say it is retrying: `onRetry` is fire-and-forget and the component re-renders identically, so a second failure looks like a dead button.                                                         |
| A dropped connection | `describeFailure` gives it `id: null`, and `ErrorState` keys its retry button on `failure.id ?? 'once'` — two consecutive network failures share a key, so the countdown and the button never re-mount.              |

## Files to touch

| File                                                                    | Change                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/components/states/error-state.tsx`                                 | A `retrying` prop: while it is true the control says it is re-attempting and is disabled. Key the retry on the failure's identity **or** an attempt counter, so a second failure of the same kind still re-mounts.                                                                                                                                                                                                        |
| `src/components/states/states.test.tsx`                                 | Retrying is announced; a second failure re-arms the control; a non-HTTP failure still offers a retry.                                                                                                                                                                                                                                                                                                                     |
| `src/app/(app)/search/query-form.tsx`                                   | Stop replacing the form: the capture-point fieldset owns its loading, empty and failed states; the window, conditions, estimate and run control stay on screen (the run control already refuses a query with no points chosen).                                                                                                                                                                                           |
| `src/app/(app)/search/sensor-list.tsx` (new)                            | The fieldset extracted with its three states, so the form body has one child to render instead of three early returns.                                                                                                                                                                                                                                                                                                    |
| `src/app/(app)/search/query-form.test.tsx`                              | With the capture-point read refused: the fieldset reports it, the window inputs and the run control are still there, the run control still refuses; a retry re-reads and the list appears.                                                                                                                                                                                                                                |
| `src/app/(app)/sessions/[id]/session-view.tsx`                          | Keep the frame when the session read fails: the way back stays, the failure is reported in the body, and the retry says it is retrying.                                                                                                                                                                                                                                                                                   |
| `src/app/(app)/sessions/[id]/session-view.test.tsx`                     | A refused session read leaves the back control on screen and offers a retry that reports itself.                                                                                                                                                                                                                                                                                                                          |
| `src/app/(app)/sessions/[id]/flow-timeline.tsx`, `related-sessions.tsx` | Pass `retrying` through to their error states — they already contain their failures, they just cannot say they are trying again.                                                                                                                                                                                                                                                                                          |
| `e2e/chaos.spec.ts` (new)                                               | Serial, and restoring calm in `afterAll` whatever happens: (a) every read refused — the search form survives and reports; (b) the same on a session; (c) a retry after the refusals are lifted brings the screen back; (d) a pass over sign-in, search and a session with a 15 s access token shows no failure; (e) a search that fails mid-scan reports as failed (forced with the search failure rate, not waited for). |
| `e2e/search-flow.ts`                                                    | Two helpers for the chaos specs: set a profile with overrides, and restore. Nothing else changes.                                                                                                                                                                                                                                                                                                                         |
| `CLAUDE.md`, `plans/000-roadmap.md`                                     | One convention line; mark 4.1 done. At the end, not during.                                                                                                                                                                                                                                                                                                                                                               |

Deliberately **not** touched: `src/lib/query-retry.ts` (the policy already retries 503 and network
failures and refuses to retry a plain 4xx, and the backend scores it as correct), the session store's
refresh (proved fine under expiring tokens), and the toast path.

## Steps

1. **Reproduce deterministically first.** Set `get_503_rate: 1.0` and drive `/search` and a session
   with request logging, to confirm the four observations above and to catch anything the statistical
   run hid. This is a diagnosis step: no code yet.
2. **Fix the retry's silence.** `ErrorState` gains `retrying`; the retry key becomes the failure's
   identity when it has one and an internal attempt count when it does not. Test first — a second
   identical network failure must re-arm the control.
3. **Split the capture-point list out of the form.** `sensor-list.tsx` takes the query's state and
   renders the fieldset, its loading skeleton, its empty case and its failure with a retry. The form
   keeps rendering everything else regardless.
4. **Stop the form's early returns.** Remove the two screen-wide returns from `query-form.tsx`; the
   remaining guard logic (`describeQuery`) already refuses to run a search without a capture point, so
   nothing can be started from a broken list.
5. **Keep the session's frame.** In `session-view.tsx` the failed read renders inside the same layout
   as the happy path: the way back, then the failure. Pass `retrying` here and into the timeline and
   the neighbours.
6. **Then the end-to-end specs**, with the deterministic override — including the mid-scan failure,
   forced with the search failure rate rather than waited for.
7. **Verify under both profiles**, then the two documentation lines.

## Risks

- **Flaky tests by construction.** Anything asserted against a probability is a coin toss. Every
  chaos assertion uses an override that makes the outcome certain, and the profile is restored in
  `afterAll` even when a test throws — otherwise the rest of the suite inherits the storm.
- **A retry storm of our own.** Making the attempt visible must not make it more frequent: the policy
  and its backoff stay untouched, and the e2e counts the requests behind one failure to prove we did
  not start retrying harder. `http.retry_after_violations` and `http.retried_4xx` are the backstop.
- **A partially rendered screen asking for something impossible.** With no capture points on screen,
  the estimate and the run control must not fire. They are already gated on a complete query; the test
  for step 4 pins that down.
- **Polling under refusal.** A search being watched while every read is refused must not spin: the
  interval comes from the job's own state, and a failed read leaves the last state in place. Worth an
  explicit look during step 1.
- **The dropped connection.** It arrives as a network error, not an `HttpError`, so it has no code, no
  advertised delay and no identity — that is precisely the case step 2 fixes, and it is the one the
  `storm` profile produces one time in twenty.
- **Expiring tokens with a long read.** A 15 s token against a search that takes longer means the
  refresh happens mid-flight; the single-flight refresh already covers it and the report's
  `auth.refresh_single_flight` and `auth.refresh_reuse` are the evidence.
- **Leaving chaos on.** A crashed run that never restores would poison every later `capture-api
report`. The restore is in `afterAll`, and the plan's verification runs the report after the suite.

## Verification

| Spec criterion                                        | Proof                                                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — the search form survives a refused read           | Component test with the capture-point read refused; e2e with every read refused: the window inputs and the run control are still on screen. |
| 2 — a session shows what arrived                      | Component test: the back control survives a refused session read; the timeline and neighbours already have their own tests.                 |
| 3 — a refusal recovers by itself                      | E2E: with one read refused and the refusals then lifted, the screen fills without a click (the policy's own retry).                         |
| 4 — a second failure is not silence                   | Component test on `ErrorState`: the control re-arms and announces the re-attempt.                                                           |
| 5 — a dropped connection is a refusal                 | Component test with a rejected fetch: retryable, with a working retry.                                                                      |
| 6 — a refused search can be run again (no regression) | The existing run-search specs, unchanged.                                                                                                   |
| 7 — a search failed mid-scan says so                  | E2E with the search failure rate forced to 1: the progress panel reports failed with the server's reason.                                   |
| 8 — expiring tokens stay invisible (no regression)    | E2E: a full pass under a 15 s token, asserting no failure surfaced and no bounce to sign-in.                                                |
| 9 — the verdict stays clean under both profiles       | `capture-api report` after the chaos suite: no FAIL, watching `http.retry_after_violations`, `http.retried_4xx`, `auth.refresh_reuse`.      |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
