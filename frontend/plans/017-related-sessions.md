# 017 — Related sessions (implementation plan)

Read this before implementing. The spec is `specs/017-related-sessions.md`.

## Decisions taken (the spec's open questions, answered)

- The window stays **local to the screen**: the address names the session and nothing else. No
  mirroring, no router push per click.
- The rows are a **compact fixed line** — time, protocol, endpoints, size, risk — not the server's
  published column set. This is a short list beside a session, and it costs no extra read.

## What the contract and the live server say (probed 2026-09-21)

| Fact                                               | Consequence                                                                                           |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `window` is one of `15m`, `1h`, `6h`, default `1h` | The three widths are the only ones offered; `2h` answers **422**.                                     |
| Paged with `cursor` / `next_cursor`                | Same discipline as the results table: the marker goes back verbatim, and it belongs to one window.    |
| Items are `SessionRow`                             | The same shape the results table already formats, so the row reader is already there.                 |
| The session is absent from its own list            | No self-filtering needed; the list is shown as it arrives.                                            |
| An unknown session answers **404**                 | The list must not turn that into an error screen on a page that is already showing "no such session". |
| Seven items at every window for a real TCP session | `next_cursor` is often `null`; paging still has to work, so it is proven with a stub.                 |

The proxy does **not** yet validate this path and the key factory has no entry for it — both are
part of this change.

## Files to touch

| File                                                          | Change                                                                                                                                                                                             |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/api/keys.ts`                                         | `sessionRelatedKey(sessionId, window)` — nested under the session, with the window as part of the identity so a marker cannot cross windows.                                                       |
| `src/lib/api/keys.test.ts`                                    | Two windows are two entries; both sit under the session's prefix.                                                                                                                                  |
| `src/lib/api/response-schemas.ts`                             | One row: the related path validated with the generated schema (the screen now depends on this read).                                                                                               |
| `src/lib/api/response-schemas.test.ts`                        | The path resolves to a schema, and is told apart from the session and the flow paths.                                                                                                              |
| `src/lib/session/related.ts` (new)                            | `RELATED_WINDOWS` (the three the server names, with their labels) and `describeRelated(row)` — the compact line's parts, built from the row the server already sends.                              |
| `src/lib/session/related.test.ts` (new)                       | Each window is one the contract allows; the line's parts for a real row, including an endpoint with a host name and one without, and a row with zero bytes.                                        |
| `src/lib/session/use-related.ts` (new)                        | Infinite read keyed by session and window; `getNextPageParam` from `next_cursor`; the marker passed back untouched; `staleTime: Infinity`; disabled without a session.                             |
| `src/lib/session/use-related.test.tsx` (new)                  | The window reaches the request; the marker is sent verbatim on the second page; two windows are two entries and one window is read once; no page is asked for when the server says there are none. |
| `src/app/(app)/sessions/[id]/related-sessions.tsx` (new)      | The client leaf: the window control, the list of links, "read on" when there is more, and its own loading, empty, failed and 404 states.                                                           |
| `src/app/(app)/sessions/[id]/related-sessions.test.tsx` (new) | Renders real rows as links to their own ids; the window control re-reads; more pages append; empty says so; a failure retries in place.                                                            |
| `src/app/(app)/sessions/[id]/session-view.tsx`                | Render the list after the timeline, given the session's id.                                                                                                                                        |
| `e2e/session-view.spec.ts`                                    | On a real session: the list is there, an entry leads to the id it names, and every `window` sent is one the server accepts (no 4xx in the run).                                                    |
| `CLAUDE.md`, `plans/000-roadmap.md`                           | One convention line; mark 3.4 done, and note phase 3 is complete. At the end, not during.                                                                                                          |

Not touched: the search screen, the results table, the summary, the protocol views.

## Steps

1. **The cache identity first.** Add `sessionRelatedKey` and its test. The window belongs in the key
   for the same reason the sort order does in the results table: a marker issued for one window is
   meaningless in another, and the server would refuse it.
2. **Validate the read.** Add the route row in the response schemas with the generated schema, and a
   test that it is picked for the related path and not for the session or the flow path.
3. **The pure part, test-first.** `related.ts` holds the three windows with their labels and turns a
   row into the parts of one line. Endpoints carry a host name only sometimes, so the line falls back
   to the address; sizes and risk reuse the shared formatters rather than new ones.
4. **The read.** `use-related.ts` mirrors the results table's infinite query: `initialPageParam`
   undefined, the marker from `next_cursor`, and nothing invented when it is null. `staleTime` is
   infinite — the sessions around a closed session do not change.
5. **The leaf.** `related-sessions.tsx` is `'use client'` for the window control. Each row is a link
   to `/sessions/{id}` built from the id as a string. A session the server does not have (404) is
   stated quietly rather than raised: this list can be on screen for a page that is itself about to
   say "no such session".
6. **The states in the same step**: reading, nothing around this session, more to read, and a failure
   with one retry that leaves the summary, the protocol view and the timeline untouched.
7. **Wire into the session screen** after the timeline.
8. **E2E**, then verify, then the two documentation lines.

## Risks

- **A marker crossing windows (scored).** Structurally impossible once the window is in the key —
  each window has its own page chain. The alternative (one query with a window parameter) would send
  a marker from `6h` to `15m` and earn an `invalid_cursor`.
- **A refused window (422), and worse, a retried one.** Only the three published widths are ever
  offered; the shared retry policy refuses to retry a 4xx, and the e2e asserts no 4xx came back from
  this path.
- **A request per redraw.** The window is the only thing in the key; the list itself is derived. A
  re-render must not refetch, which the hook test pins down.
- **Ids as numbers.** These rows carry uint64 ids as strings and the links are built from them
  verbatim — the same trap as the results table. The e2e compares the link's target with the address
  it lands on.
- **A 404 becoming an error screen.** The related read for a missing session answers 404; the list
  must state it instead of putting a retry button on a page that already says the session is gone.
- **Cache growth.** Three windows per session, held for the visit, each a page or two — negligible,
  and the shared `gcTime` drops them on leaving.
- **Chaos.** Under `storm` this read fails while the rest of the session renders — that separation is
  why the list owns its error state. Under `expiring-tokens` it goes through the usual single refresh
  on the server.

## Verification

| Spec criterion                                | Proof                                                                                                                                |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1 — the list is there, with the right parts   | Component test over real rows; e2e on a session opened from the results.                                                             |
| 2 — an entry opens that session               | Component test asserts each link's target is the row's id; e2e clicks one and compares the address.                                  |
| 3 — the window changes, nothing refused       | Component test (the control re-reads with the new window); e2e asserts every `window` sent is one of the three and no 4xx came back. |
| 4 — reading on uses the server's marker       | Hook test: the second page carries the marker verbatim and the list appends.                                                         |
| 5 — an empty window says so                   | Component test with an empty page.                                                                                                   |
| 6 — a failure is contained                    | Component test: the retry is in the list, the rest of the screen is untouched.                                                       |
| 7 — a window already read asks nothing        | Hook test with a shared client: going back to the first window sends no third request.                                               |
| 8 — no reason for the relationship is claimed | Component test: the list's text contains no explanation, only the rows and the window control.                                       |
| 9 — the verdict stays clean                   | `capture-api report` after the e2e run: no FAIL, watching `http.invalid_cursor`, `http.retried_4xx`, `http.get_dedupe`.              |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
