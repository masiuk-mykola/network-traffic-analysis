# Plan 010 — Starting a search

Spec: `specs/010-run-a-search.md`. Its open questions were answered: a running search is kept while the
query is edited and replaced only when a new one is started, the idempotency label is derived from the
query so it lives exactly as long as the query is unchanged, and leaving the screen leaves the job
alone — its id is in the address bar, so it can be picked back up.

## Files to touch

| Path                                              | Change                                                                                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `src/app/api/searches/route.ts` (new)             | `POST` a search: passes the body through with an `Idempotency-Key`, returns the created job, maps refusals like the proxy does. |
| `src/app/api/searches/[id]/route.ts` (new)        | `GET` one search and `DELETE` it — the proxy only speaks GET, and freeing a slot needs the other verb.                          |
| `src/lib/search/search-body.ts` (new)             | `toSearchBody(state, fields)` → what `POST /v1/searches` takes, or null; `idempotencyKeyFor(body)` derives the label.           |
| `src/lib/search/search-body.test.ts` (new)        | Every field of the body, the sort default, and that the same query yields the same label while a changed one does not.          |
| `src/lib/search/use-run-search.ts` (new)          | The mutation: ends the previous job, starts the new one, writes its id into the address bar.                                    |
| `src/lib/search/use-search.ts` (new)              | Reads one search by id, so a reload can pick up what is already running.                                                        |
| `src/lib/search/query-params.ts`                  | The query state carries the started search id (`search=`), parsed and written with the rest.                                    |
| `src/app/(app)/search/run-control.tsx` (new)      | The button, its in-flight state, the refusal messages, and the warnings the job reports.                                        |
| `src/app/(app)/search/run-control.test.tsx` (new) | One job per double press, a retry that replays rather than duplicates, the slot refusal, warnings.                              |
| `src/app/(app)/search/query-form.tsx`             | Hosts the control in place of the inert button and hands it the query.                                                          |
| `e2e/run-search.spec.ts` (new)                    | A real job against the API: started, replaced, reloaded, and nothing left abandoned.                                            |
| `CLAUDE.md`                                       | One line: writes go through their own handlers, and a search is labelled by its query.                                          |

## Steps

1. **`search-body.ts`** (test first) — `toSearchBody` reuses the completeness rules already shared by
   the form and the estimate, then builds `{ sensor_ids, from, to, filter, sort }`; `filter` comes from
   the condition model, defaulting to an empty `all` when there are no conditions, and `sort` defaults
   to newest first. `idempotencyKeyFor` hashes the serialized body into the format the API accepts
   (`^[A-Za-z0-9_-]{8,64}$`) — same query, same label; edited query, different label.
2. **`api/searches/route.ts`** — a `POST` handler that validates nothing of its own: it forwards the
   body, sets the `Idempotency-Key` header it is given, and returns the created job with its status.
   A replay answers 200 rather than 202 and says so in a header; both are success.
3. **`api/searches/[id]/route.ts`** — `GET` by id for picking a job back up, and `DELETE` to free a
   slot. Both map failures through the shared error payload, like the read proxy.
4. **`use-run-search.ts`** — a mutation that, in order: deletes the previously started job if this
   screen still has one, posts the new search with its derived label, and writes the returned id into
   the address bar. `retry: false`; a retry is the person pressing again, and the label makes that
   safe. Nothing is polled here.
5. **`use-search.ts`** — a query keyed by the id from the address bar, enabled only when there is one,
   so a reload shows the job that is already running. No polling yet: following it is the next item.
6. **`query-params.ts`** — `search=<id>` joins the state, so the started job travels with the query.
7. **`run-control.tsx`** — the button (disabled while the query is incomplete or the mutation is in
   flight, labelled with what it is doing), the job's state once started, its warnings listed plainly,
   and the refusals: out of slots shows the stated wait and no immediate retry; a 503 offers one.
8. **`query-form.tsx`** — replace the inert submit with the control, passing the query and the fields.
9. **Tests** — unit for the body and the label, component tests for the control, e2e for the whole
   thing.
10. **`CLAUDE.md`** line.

## Risks

- **Two jobs from one intent.** A double press, or a retry after a timeout, must not spend two of three
  slots. The derived label is the defence, and the mutation refuses to run while one is in flight.
  `search.duplicate_jobs` is the check.
- **A job nobody reads.** Starting a second search without ending the first leaves it running to
  completion for nothing; `search.abandoned` counts exactly that. The delete happens before the new
  post, not after, so a failure to start does not leave two.
- **Deleting what is not ours.** The id in the address bar can be edited. A delete is only issued for a
  job this screen started in this session, not for whatever the URL happens to name.
- **Out of slots.** The refusal carries a wait in seconds; the control must count it down rather than
  offer an immediate retry, which the shared failure handling already does — but the button is separate
  from that error state and needs the same treatment.
- **A slow start under `--chaos storm`.** A 503 is retryable, and the label is what makes retrying safe;
  without it the retry creates a twin, which is precisely what the backend flags.
- **The address bar as the source of truth.** The id is written with the same shallow update as the rest
  of the query, so writing it does not re-render the page on the server; a reload reads it back.
- **Losing the job on sign-out.** The session ending cancels queries and clears the cache; the job stays
  on the server and its slot frees when it finishes. Nothing here should try to delete it during that.

## Verification

| #   | Acceptance criterion                         | How it is proven                                                                                                                                         |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A complete query starts and shows as running | Control test with a stubbed 202. E2E: a real search appears with its id in the address bar.                                                              |
| 2   | Two presses make one job                     | Control test: the second press while in flight sends nothing. E2E: double click, then one job on the server.                                             |
| 3   | A retry replays rather than duplicates       | Unit: the same query yields the same label. E2E: force a failure, retry, and see the replay header.                                                      |
| 4   | Starting a second search ends the first      | Control test: the delete is issued before the post. E2E: two searches in a row, and the first is gone.                                                   |
| 5   | Out of slots is explained with its wait      | Control test with a 429 carrying `Retry-After`: the wait is shown and no retry is offered.                                                               |
| 6   | A momentary failure retries without a twin   | Control test with a 503 then a success: one job, same label.                                                                                             |
| 7   | Warnings are visible                         | Control test with a job carrying warnings: each is rendered.                                                                                             |
| 8   | A reload returns to the same search          | E2E: start, reload, and the same id is still in the address bar and still shown.                                                                         |
| 9   | Nothing is left abandoned                    | E2E then `capture-api report`: `search.abandoned` and `search.duplicate_jobs` not FAIL.                                                                  |
| —   | Nothing else regressed                       | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL. |
