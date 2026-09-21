# Plan 012 — The results table

Spec: `specs/012-results-table.md`. Its open questions were answered: while the search runs and the
reader has caught up, the table keeps reading quietly on the same backoff the progress uses; sorting
is offered but disabled until the search finishes, with the reason shown; and the rows are windowed.

## Files to touch

| Path                                                | Change                                                                                                                        |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `package.json`                                      | Add `@tanstack/react-virtual`.                                                                                                |
| `src/lib/search/row-value.ts` (new)                 | Maps a published column key to the value in a row, then through the shared formatter. Unknown key or type falls back to text. |
| `src/lib/search/row-value.test.ts` (new)            | Every published column, the undocumented type, a missing optional, and a key nothing maps to.                                 |
| `src/lib/search/use-columns.ts` (new)               | The column catalogue, cached long like the field one.                                                                         |
| `src/lib/search/use-results.ts` (new)               | The paged read: infinite query on the opaque cursor, page size, and the quiet catch-up while the job runs.                    |
| `src/lib/search/use-results.test.tsx` (new)         | Cursor passed back verbatim, the three page endings, the catch-up interval, and that it stops when the job ends.              |
| `src/app/(app)/search/results-table.tsx` (new)      | The table: header from the catalogue, windowed rows, the end-of-list line, and every state.                                   |
| `src/app/(app)/search/results-table.test.tsx` (new) | Columns from the catalogue, still-looking vs nothing-matched, end of list, a failed page, row navigation.                     |
| `src/app/(app)/search/query-form.tsx`               | Renders the table under the form when a search exists.                                                                        |
| `e2e/results-table.spec.ts` (new)                   | Real rows from a real search: they appear while it runs, more load on scroll, and a row opens its session.                    |
| `CLAUDE.md`                                         | One line: results are cursor-paged and windowed; columns come from the server.                                                |

## Steps

1. **Install** `@tanstack/react-virtual`. Nothing else; the table itself is ours.
2. **`row-value.ts`** (test first) — one map from column key to the value it reads out of a row
   (`sensor` → the row's sensor id, `src`/`dst` → the endpoint objects, `duration` → the millisecond
   count, `files` → the file count, `dst_country` → the destination's country, and so on), then
   `formatByColumnType` for the presentation. A key with no mapping, or a type the formatter does not
   know — the live server publishes one — ends up as text rather than blank.
3. **`use-columns.ts`** — the catalogue, `staleTime` long, keyed by the existing factory.
4. **`use-results.ts`** — `useInfiniteQuery` keyed by the search id and sort. `getNextPageParam`
   returns the cursor the server sent, untouched, and `undefined` when the page says it is the end or
   says it has caught up. Page size is a constant at the server's maximum; the applied size comes back
   in a header and is what the code trusts. While the job is running and the last page was a catch-up,
   a refetch interval on the same backoff as the progress reads the tail; once the job ends, no
   interval at all.
5. **`results-table.tsx`** — header cells from the catalogue in its own order, honouring default
   visibility and width hints; sortable columns render as buttons, disabled while the job runs with a
   title explaining that a different order needs a finished search. Rows are windowed with a fixed row
   height; the scroll container asks for the next page when the last rendered row is near the end.
   States: still looking (job running, nothing yet), nothing matched (job finished, nothing), end of
   list, and a failed page shown beneath the rows already loaded with a retry.
6. **`query-form.tsx`** — render the table below everything else when the query names a search.
7. **Tests** — unit for the mapping, hook tests for the paging rules, component tests for the table,
   e2e against real rows.
8. **`CLAUDE.md`** line.

## Risks

- **A cursor that is not passed back exactly.** Cursors are opaque and bound to the search and its
  order; re-encoding one produces `invalid_cursor`, which the backend scores. It goes straight from
  the response into the next request, never through a URL parameter or a state transform.
- **Asking for more than the server allows.** The cap is five hundred and the server clamps silently,
  reporting what it applied. Requesting more is scored (`http.limit_over_max`), so the constant is the
  cap, not a guess above it.
- **A page loop.** "Caught up" looks like "there might be more", and an infinite query that treats it
  as a next page would spin. The catch-up case returns no page parameter and is handled by a timed
  refetch instead, which stops the moment the job ends.
- **Duplicate page requests.** A scroll handler that fires per frame would ask repeatedly for the same
  cursor. The request is guarded by the query's own in-flight state, and the trigger is a threshold on
  the last rendered row rather than a raw scroll event.
- **Sorting while running.** The server answers 409. The controls are disabled until the job finishes
  rather than letting someone discover that by clicking.
- **Rows that outlive their search.** A job can be discarded for being unread; the table must then stop
  asking and show the ending rather than an error loop. The same 410 handling as the progress applies.
- **Windowing and the row height.** A wrong fixed height makes the scrollbar lie. The row height is a
  constant shared between the measurement and the style, not two numbers that can drift.
- **Chaos.** Under `storm` a page can fail mid-scroll; the rows already loaded stay, the failure shows
  beneath them, and the retry asks for the same cursor again.

## Verification

| #   | Acceptance criterion                                | How it is proven                                                                                                                                                                                                                            |
| --- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Rows appear while the search runs                   | Hook test: a page returned while the job is running is rendered. E2E: rows are on screen before "finished".                                                                                                                                 |
| 2   | More rows load at the end of what is shown          | Component test: reaching the threshold asks for the next cursor. E2E: scrolling loads a second page.                                                                                                                                        |
| 3   | The cursor goes back byte for byte                  | Hook test with a cursor containing characters that would not survive re-encoding.                                                                                                                                                           |
| 4   | No page exceeds the server's maximum                | Hook test: the request carries the cap. Then `capture-api report` with `http.limit_over_max` not FAIL.                                                                                                                                      |
| 5   | Thousands of rows stay usable                       | Component test with five thousand rows: only a window of them is in the document.                                                                                                                                                           |
| 6   | Columns come from the server, unknown types as text | Component test with the real catalogue shape including the undocumented type. E2E: that column shows its value.                                                                                                                             |
| 7   | Still looking differs from nothing matched          | Component test for both.                                                                                                                                                                                                                    |
| 8   | The end of the list says so                         | Component test with a complete page.                                                                                                                                                                                                        |
| 9   | A failed page keeps what is shown                   | Component test: rows remain, failure below, retry present.                                                                                                                                                                                  |
| 10  | A row opens its session                             | Component test: the row links to the session. E2E: clicking navigates.                                                                                                                                                                      |
| 11  | Nothing is asked without a search                   | Hook test: no request without an id. E2E: no results request before starting.                                                                                                                                                               |
| —   | Nothing else regressed                              | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL — `http.invalid_cursor`, `http.limit_over_max` and `http.get_dedupe` in particular. |
