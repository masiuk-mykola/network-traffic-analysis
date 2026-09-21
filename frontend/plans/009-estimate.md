# Plan 009 — Sizing a search before running it

Spec: `specs/009-estimate.md`. Its open questions were answered: the estimate refreshes only when the
query changes, it sits next to the run control where the decision is made, and the number is rounded
so it reads as the estimate it is.

## Files to touch

| Path                                                | Change                                                                                                                   |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `src/lib/search/estimate-params.ts` (new)           | Turns the query state into what the endpoint takes — window, points, and the same `f` shorthand the address bar carries. |
| `src/lib/search/estimate-params.test.ts` (new)      | A complete query, every way an incomplete one produces nothing, and that unfinished conditions are left out.             |
| `src/lib/search/use-estimate.ts` (new)              | The query, disabled until the request is complete, keyed by the exact parameters, never refetched on its own.            |
| `src/lib/use-debounced.ts` (new)                    | A settle delay, so typing produces one request rather than one per keystroke.                                            |
| `src/lib/use-debounced.test.ts` (new)               | Rapid changes collapse to the last value; a single change still arrives.                                                 |
| `src/lib/format/count.ts` (new)                     | `formatApproximate(n)` — exact under a threshold, rounded above it, always readable.                                     |
| `src/lib/format/count.test.ts` (new)                | Small numbers exact, large ones rounded, zero, and the boundary.                                                         |
| `src/lib/format/index.ts`                           | Export it with the rest.                                                                                                 |
| `src/app/(app)/search/estimate-line.tsx` (new)      | The line itself: matches, what would be scanned, the loading and failure states.                                         |
| `src/app/(app)/search/estimate-line.test.tsx` (new) | Each state, the rounding, and that an old number is not shown while a new one is loading.                                |
| `src/app/(app)/search/query-form.tsx`               | Hosts the line above the run control and hands it the settled query.                                                     |
| `e2e/estimate.spec.ts` (new)                        | A real estimate for a real query, a zero estimate, and a burst of changes producing few requests.                        |
| `CLAUDE.md`                                         | One line: the estimate is debounced and never polled.                                                                    |

## Steps

1. **`estimate-params.ts`** (test first) — `toEstimateParams(state, fields)` returns `URLSearchParams`
   or null. Null when there is no point, no window, a backwards window, or any condition that is not
   finished — the same rules the form already uses to block the run control, so the two cannot
   disagree. Finished conditions are serialized with the existing shorthand writer.
2. **`use-debounced.ts`** (test first) — a value that only updates once its input has stopped changing
   for a set delay. 400 ms: comfortably under a second, so a settled query is answered promptly, and
   far above a keystroke.
3. **`use-estimate.ts`** — `useQuery` keyed by the serialized parameters, `enabled` only when they
   exist, `staleTime: Infinity` and no refetch on focus or interval: this capture does not move, so a
   second request for the same query would be pure waste. The retry policy already refuses to repeat a
   4xx and waits out a stated delay, which is what keeps a refusal from becoming a storm.
4. **`count.ts`** (test first) — under 1000 the exact number; above it, two significant figures with a
   thousands separator. The caller adds the "≈".
5. **`estimate-line.tsx`** — three states in one line: while fetching, a quiet "estimating…" with no
   number at all; on success, the rounded match count and, beneath it, what the server would read to
   answer for real; on failure, the shared error state with a retry, sized down so it does not take
   over the form.
6. **`query-form.tsx`** — compute the settled query with the debounce, pass it to the line, and render
   the line directly above the run control.
7. **Tests** — unit for the three pure pieces and the line; e2e against the real API.
8. **`CLAUDE.md`** line.

## Risks

- **Asking too often.** The endpoint allows four per second per session and the backend scores every
  refusal (`estimate.rate`). The debounce plus a key that only changes with the query is the whole
  defence; a missing dependency in the key would turn every render into a request.
- **A stale number read as current.** The most dangerous failure here is silent: showing the previous
  estimate while a new one loads invites a decision based on the old query. The line drops the number
  while fetching rather than dimming it.
- **Fetching for an impossible query.** A request built from an unfinished condition would be refused
  with a 400 that the person can do nothing about. The parameters module returns null instead, so
  nothing is sent.
- **Disagreeing with the run control.** Two places deciding "is this query complete" drift apart. The
  estimate reuses the form's own rules rather than reimplementing them.
- **A refusal for rate.** A 429 here carries a wait; the shared failure handling already declines to
  retry before it elapses, and the line must not offer an immediate retry either.
- **Chaos.** Under `storm` the estimate can fail while the rest of the form is fine; it is a side
  panel, not a gate, so its failure never blocks building or running a search.

## Verification

| #   | Acceptance criterion                             | How it is proven                                                                                                                                                                |
| --- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A complete query shows a match count             | Line test with a stubbed response. E2E: a real query against the running API shows a number.                                                                                    |
| 2   | An incomplete query sends nothing                | Unit: the parameters are null for each incomplete shape. Line test: no request is made.                                                                                         |
| 3   | The number reads as an estimate                  | Line test: the text carries the approximation mark and the word.                                                                                                                |
| 4   | The scanned cost is shown                        | Line test and E2E: both numbers are present.                                                                                                                                    |
| 5   | A burst of changes stays inside the allowed rate | Unit: the debounce collapses ten changes into one. E2E: type through several changes and count requests — at most two. Then `capture-api report` with `estimate.rate` not FAIL. |
| 6   | No stale number while loading                    | Line test: during the fetch the old count is absent, not dimmed.                                                                                                                |
| 7   | Zero is stated plainly                           | Line test with a zero response: the text says no sessions match.                                                                                                                |
| 8   | A failure leaves the form usable                 | Line test with a 503: the error state renders, the run control is unaffected.                                                                                                   |
| 9   | A rate refusal is waited out                     | Line test with a 429 carrying a delay: no retry control before it elapses.                                                                                                      |
| —   | Nothing else regressed                           | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL.                        |
