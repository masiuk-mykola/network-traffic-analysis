# 016 — The flow timeline (implementation plan)

Read this before implementing. The spec is `specs/016-flow-timeline.md`.

## Decisions taken (the spec's open questions, answered)

- **One shared scale, mirrored**: up above a baseline, down below it, so the two directions stay
  comparable. The totals are stated in text, which is where the smaller direction stays legible.
- **A few named widths**, derived from the session's duration and always inside the range the server
  accepts — so a refused width is impossible and the cache has a handful of predictable entries.

## What the contract and the live server say (probed 2026-09-21)

| Fact                                           | Consequence                                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `bucket_ms` is 100–60000, default 1000         | The offered widths are clamped into that range; 99 and 60001 each answer **422**.                 |
| "Empty buckets are omitted"                    | Consecutive samples are not consecutive moments; the picture is positioned by time, not by index. |
| A 127 s TLS session: 76 samples at 1000 ms     | Gaps are real in this capture, not hypothetical.                                                  |
| The same session: 208 at 100 ms, 3 at 60000 ms | The width decides whether the picture is readable, so it is derived, not fixed.                   |
| A 58 ms session: 1 sample at every width       | One bucket is a legitimate answer and must read as "nothing to plot".                             |
| `bytes_up` 23 MB against `bytes_down` 11 kB    | A shared scale flattens the smaller direction; hence the totals in text.                          |
| `t` is epoch milliseconds                      | The x axis is time; the session's own start and end bound it.                                     |

## Files to touch

| File                                                       | Change                                                                                                                                                                                                                                         |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/session/flow.ts` (new)                            | The pure part: `bucketChoices(durationMs)` (a few widths inside 100–60000, chosen from the duration), and `toSeries(samples, bucketMs, metric)` → positioned columns with their moment, both directions, and a shared peak; gaps left as gaps. |
| `src/lib/session/flow.test.ts` (new)                       | Width choice for a 58 ms, a 2 s, a 127 s and an hour-long session; every choice inside the range; gaps preserved; one-sample and empty series; a metric switch; the peak spanning both directions.                                             |
| `src/lib/session/use-flow.ts` (new)                        | The read, keyed by session and width, `staleTime: Infinity` (a closed session's traffic cannot change), no read until a width is chosen.                                                                                                       |
| `src/lib/session/use-flow.test.tsx` (new)                  | The width reaches the request; two widths are two entries and one width is read once; no read without a session.                                                                                                                               |
| `src/app/(app)/sessions/[id]/flow-timeline.tsx` (new)      | The client leaf: the mirrored columns, the width control, the bytes/packets control, the totals, and the per-bucket figures as text. Loading, empty, one-bucket and failed states live here.                                                   |
| `src/app/(app)/sessions/[id]/flow-timeline.test.tsx` (new) | Renders from a real series; a gap leaves a hole; the metric control changes what is drawn; one sample says so; a failure offers a retry and keeps the rest.                                                                                    |
| `src/app/(app)/sessions/[id]/session-view.tsx`             | Render the timeline between the protocol view and the generic list, given the session's id and duration.                                                                                                                                       |
| `e2e/session-view.spec.ts`                                 | On a real session: the timeline is there, changing the width re-reads once and only widths the server accepts go out (no 422 in the run).                                                                                                      |
| `CLAUDE.md`, `plans/000-roadmap.md`                        | One convention line; mark 3.3 done. At the end, not during.                                                                                                                                                                                    |

Not touched: the API layer (the proxy already validates this path and the key factory already has an
entry for it), the summary, the DNS view, the generic renderer.

## Steps

1. **Widths first, test-first.** `bucketChoices` takes the session's duration and returns two to four
   widths, coarsest first, each clamped into the server's range and each chosen so the picture lands
   in a readable number of columns. A session shorter than one minimum bucket gets the minimum and
   nothing else — there is no second width worth offering.
2. **The series, test-first.** `toSeries` turns samples into columns carrying their moment, their two
   directions for the chosen metric, and the series' peak across both directions. A sample the server
   omitted stays omitted: each column knows its own position in time, so the renderer can leave a
   hole rather than close the ranks.
3. **The read.** `use-flow` follows the shape of the other session reads: keyed by session and width,
   never refetched (the traffic of a closed session is history), and disabled until a width exists.
   Two widths are two cache entries, which is what makes going back to a width free.
4. **The leaf.** `flow-timeline.tsx` is `'use client'` because of the two controls. Columns are
   positioned from each one's moment across the session's own span, mirrored about a baseline, with
   the peak setting the height of both halves. Every column is also a row of text — moment, up, down
   — in a list the keyboard can walk, which is how the figures stay available without a pointer.
5. **The states, in the same step**: reading, nothing recorded, a single bucket ("too short to plot"),
   and a failure with one retry that leaves the summary and the transaction untouched.
6. **Wire into the session screen** below the protocol view. The session is already on screen, so the
   timeline renders its own loading state rather than delaying anything else.
7. **E2E**, then verify, then the two documentation lines.

## Risks

- **A request per redraw.** The width and metric controls are local state; only the width is part of
  the query key, and the metric changes nothing about what was fetched. Getting this wrong would
  fetch on every toggle, which `http.get_dedupe` would eventually catch.
- **A refused width (422), and worse, a retried one.** The widths are generated, never typed, and the
  shared retry policy already refuses to retry a 4xx — but a 422 in the run would still show up in
  the report, so the e2e asserts none was sent.
- **Index-as-time.** Positioning columns by array index instead of by moment would erase the gaps the
  spec exists to show. The series carries the moment; the test for gaps is the guard.
- **A dishonest scale.** One shared peak across both directions is the decision above; the smaller
  direction can round to nothing visually, which is why the totals are stated in text and each
  column's figures are readable.
- **Time arithmetic on ids.** `t` is a number, the session id is not; nothing in this reader touches
  the id.
- **Cache growth.** Four widths per session, held forever, is a handful of entries per visit; the
  shared `gcTime` already drops them when the screen is left.
- **Chaos.** Under `storm` the series fails while the session still renders — that separation is the
  point of giving the timeline its own error state. Under `expiring-tokens` the read goes through the
  usual single refresh on the server.

## Verification

| Spec criterion                                  | Proof                                                                                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1 — a timeline with both directions             | Component test over a real series; e2e on a session opened from the results.                                                   |
| 2 — the width suits the session                 | Unit test: the widths for 58 ms, 2 s, 127 s and an hour differ, and all sit inside 100–60000.                                  |
| 3 — changing the width redraws, nothing refused | Component test (the control re-reads with the new width); e2e asserts every `bucket_ms` sent is in range and no 422 came back. |
| 4 — gaps stay gaps                              | Unit test on the positioned series; component test asserts the hole is rendered.                                               |
| 5 — bytes against packets                       | Component test: the drawn figures change with the control, and no request goes out.                                            |
| 6 — figures readable, keyboard reachable        | Component test on the text list and its focusable rows.                                                                        |
| 7 — one bucket or none says so                  | Component tests for a single sample and for an empty series.                                                                   |
| 8 — a failure is contained                      | Component test: the summary and transaction survive, the timeline offers its retry.                                            |
| 9 — read once per width, verdict clean          | Unit test on the hook; `capture-api report` after the e2e run — no FAIL, watching `http.get_dedupe` and `http.retried_4xx`.    |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
