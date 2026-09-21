# 013 — Make results linkable (implementation plan)

Read this before implementing. The spec is `specs/013-linkable-results.md`.

## What the live server actually does (both open questions, closed)

Probed against the running API on 2026-09-21 with a real job on `hq-core`:

| Probe                                       | Answer                                                                      |
| ------------------------------------------- | --------------------------------------------------------------------------- |
| `sort` while the job is queued/running      | **409** `search_running` — "Read the default `-ts` order, or wait for done" |
| `sort` once the job is done                 | 200, genuinely re-ordered from the first row                                |
| a cursor from one order replayed on another | **400** — and an invalid cursor is a scored check                           |
| unknown id / another account's id / deleted | **404** `search_not_found` (not 410)                                        |
| `sort` outside the published vocabulary     | 422                                                                         |
| allowed values                              | `ts`, `-ts`, `bytes`, `-bytes`, `risk`, `-risk`; create defaults to `-ts`   |

Consequences that drive the design below: the order is part of the **cache identity** (a cursor may
never cross orders), the control must be inert until `done`, and a job that is simply gone reaches
us as a 404, which today falls through to a generic error screen.

The second open question (restoring scroll position on back) is taken as **out of scope**, per the
spec.

## Files to touch

| File                                          | Change                                                                                                                                                                                                                        |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/search/sort.ts` (new)                | The order vocabulary: `SORT_KEYS`, `parseSortKey`, the column-key → sort-field map (`start`→`ts`, `bytes`→`bytes`, `risk`→`risk`), `toggleSort`, `directionOf`.                                                               |
| `src/lib/search/sort.test.ts` (new)           | Unknown value, unknown column, toggling a direction, toggling to a different column, back to the default.                                                                                                                     |
| `src/lib/search/query-params.ts`              | `QueryState` gains `sort: SortKey \| null`; `parseQuery` reads `sort=` defensively; `toQueryString` writes it only when it is not the default.                                                                                |
| `src/lib/search/query-params.test.ts`         | A rubbish order is dropped; a valid one round-trips; the default never appears in the address.                                                                                                                                |
| `src/lib/api/keys.ts`                         | `searchResultsKey(searchId, sort?)` — the second slot stops being a cursor (nothing passes one) and becomes the order, normalized to `null`.                                                                                  |
| `src/lib/api/keys.test.ts`                    | Two orders of one search are two keys; both still sit under the search's prefix.                                                                                                                                              |
| `src/lib/search/search-state.ts`              | A `MISSING` sentinel beside `EXPIRED`, with its own ending kind and wording ("the server no longer has this search").                                                                                                         |
| `src/lib/search/search-state.test.ts`         | `MISSING` is an ending, is not running, and reports zeroed progress.                                                                                                                                                          |
| `src/lib/search/use-search.ts`                | Map 404 to `MISSING` the way 410 already maps to `EXPIRED`.                                                                                                                                                                   |
| `src/lib/search/use-results.ts`               | Take the order; put it in the key; send `sort` only when the job is finished **and** the order is not the default; `staleTime: Infinity` once finished.                                                                       |
| `src/lib/search/use-results.test.tsx`         | The order reaches the request only when finished; a new order starts from no cursor; the key changes with the order.                                                                                                          |
| `src/app/(app)/search/results-table.tsx`      | Header cells become real sort controls (`aria-sort`, direction marker, disabled with a reason while running); the table renders nothing when the job is gone; the re-read shows its own loading state rather than stale rows. |
| `src/app/(app)/search/results-table.test.tsx` | Clicking a sortable header asks for the new order; a non-sortable header has no control; while running the controls are disabled and say why.                                                                                 |
| `src/app/(app)/search/query-form.tsx`         | Holds the order in the same state object as the rest of the query, so the existing address-bar mirroring carries it; passes it and the setter down.                                                                           |
| `src/app/(app)/search/search-progress.tsx`    | Render the `missing` ending — one sentence plus the standing invitation to run the query again (the run control is already on screen).                                                                                        |
| `e2e/linkable-results.spec.ts` (new)          | The five outside-observable criteria; serial, with cleanup, like the other search specs.                                                                                                                                      |
| `CLAUDE.md`, `plans/000-roadmap.md`           | One convention line; mark 2.7 done. At the end, not during.                                                                                                                                                                   |

Not touched: the session screen itself (phase 3), the `/dev/session` probe (tracked in the roadmap's
2.1 row), column visibility.

## Steps

1. **`sort.ts` first, test-first.** The whole feature hangs on a tiny pure module: which published
   column maps to which sort field, and what one click does to the current order. Write the tests,
   then the module. `toggleSort` returns descending on a fresh column (newest/biggest/riskiest first
   reads better), flips on the same column, and returns to the default when flipped off.
2. **Carry it in the query.** Extend `QueryState` and both directions of `query-params`. Parsing is
   defensive like everything else there: an order that is not in the vocabulary is dropped, not
   rejected. Writing omits the default so the common address stays short.
3. **Split the cache by order.** Change `searchResultsKey`'s second argument from an unused cursor to
   the order. This is the guard that makes a cursor incapable of crossing orders — the 400 above
   cannot happen if the two orders never share a query.
4. **Teach the results hook the order.** It sends `sort` only for a finished job (the 409 is a
   refusal we must never provoke) and only when the order differs from the default. Once the job is
   finished its pages are immutable, so `staleTime` goes to `Infinity` there: coming back from a
   session must not re-read every loaded page.
5. **Make a gone job an ending, not a failure.** 404 → `MISSING` in `use-search`, a new ending kind,
   and the wording in `search-progress`. The query is still in the address, so the run control on the
   same screen is the offer to run it again — no second button.
6. **Wire the header controls.** `results-table` receives the order and a setter. A sortable column
   gets a button with `aria-sort` and a direction marker; while the job runs it is disabled with the
   server's own reason. During the re-read the table shows its loading state instead of rows in an
   order the header no longer claims.
7. **Hold the order in the form.** `query-form` keeps it in the same state object as sensors and
   conditions, which means the existing `history.replaceState` mirroring already puts it in the
   address — no second mechanism, and no `router.replace` (that would re-render the server page and
   re-read the field catalogue, which we removed on purpose).
8. **E2E.** One serial spec: sort a finished search, reload the produced address, confirm no second
   job was created (count the create calls), open a row and come back, and open a made-up job id.
9. **Verify, then the two documentation lines.**

## Risks

- **Cursor across orders (scored).** A cursor from `-ts` replayed on `bytes` is a 400 and shows up in
  `http.invalid_cursor`. Mitigated structurally by step 3 — different orders are different queries
  with their own page chain — not by a runtime check.
- **409 from sorting a live job (scored as a retried 4xx if we then retry).** The control must be
  disabled from the job's own state, and the hook must omit `sort` unless finished. The window to get
  this wrong is the instant the job flips to `done`; both guards read the same status object.
- **A second job on an order change.** The order is not part of what starts a search: the create body
  keeps its default order, so the idempotency label does not change and no new job is created. Worth
  an explicit e2e assertion (criterion 2) because it would be invisible otherwise.
- **Refetch storm on back-navigation.** An infinite query with three loaded pages re-reads all three
  on remount if it is stale — three requests for nothing, and `http.get_dedupe` watches identical
  GETs. Handled by the `staleTime` in step 4.
- **Duplicate GETs from a double render.** The order change cancels nothing by itself; React Query
  will run the new key's first page once, but the old query stays cached. Acceptable — the old order
  is a legitimate cache entry and will be re-shown instantly if the user flips back.
- **A 404 that is really a dead session.** `session_revoked` reaches us as a 401 and is handled
  centrally; a 404 on a search must not be confused with it. The mapping is by status **and** the
  search endpoint only.
- **Chaos.** Under `storm` the first read of a new order can fail; the table's existing error state
  with retry covers it, and the retry policy already refuses to retry a 4xx. Under `expiring-tokens`
  the re-read goes through the usual single refresh.

## Verification

| Spec criterion                                  | Proof                                                                                                                                                    |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — sorting changes rows and the address        | Component test: a header click asks the hook for the new order. E2E: sort a finished search, first row changes, `sort=` appears in the address.          |
| 2 — the address restores, nothing new starts    | E2E: reload the produced address, same first row, and the count of create requests over the whole spec stays at one.                                     |
| 3 — controls inert while running, with a reason | Component test on both states (disabled + title while running, enabled once done).                                                                       |
| 4 — a re-read starts from the beginning         | Unit test on the hook: the new order's first request carries no cursor. Key test: the two orders are different cache entries.                            |
| 5 — a row leads to a session, back returns      | E2E: click a row, land on the session address, go back, the same order and rows are on screen with no further result requests.                           |
| 6 — a gone job explains itself                  | Unit test: 404 becomes the `missing` ending. E2E: open `/search?...&search=srch_000000000000` and read the sentence.                                     |
| 7 — the backend's verdict stays clean           | `capture-api report` after the e2e run: no FAIL, and specifically `http.invalid_cursor`, `http.retried_4xx`, `search.duplicate_jobs`, `http.get_dedupe`. |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
