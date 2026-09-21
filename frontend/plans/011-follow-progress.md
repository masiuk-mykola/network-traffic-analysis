# Plan 011 — Following a running search

Spec: `specs/011-follow-progress.md`. Its open questions were answered: the interval starts at half a
second and doubles to a ceiling of five, watching pauses while the tab is hidden, and a finished job
is not polled at all — reading its rows is what will keep it alive once the table exists.

## Files to touch

| Path                                                  | Change                                                                                                                |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `src/lib/search/search-state.ts` (new)                | What a job's state means for the UI: is it still running, what ended it, and what to say about it.                    |
| `src/lib/search/search-state.test.ts` (new)           | Every state, the discarded case, an estimated match count, and progress with fields the API may omit.                 |
| `src/lib/search/poll-interval.ts` (new)               | `nextPollDelay(attempt)`: 500 ms doubling to a 5 s ceiling.                                                           |
| `src/lib/search/poll-interval.test.ts` (new)          | The sequence, the ceiling, and that it never returns zero.                                                            |
| `src/lib/search/use-search.ts`                        | Grows a polling interval that backs off, stops on an end state, pauses in the background, and treats a 410 as an end. |
| `src/lib/search/use-cancel-search.ts` (new)           | The mutation that stops a running job and marks it cancelled.                                                         |
| `src/app/(app)/search/search-progress.tsx` (new)      | The progress readout: state, percentage, scanned and matched counts, the stop control, and every ending.              |
| `src/app/(app)/search/search-progress.test.tsx` (new) | Each state and ending, the estimate marker, the failure of a refresh, and that nothing is asked without a job.        |
| `src/app/(app)/search/run-control.tsx`                | Hands the job to the progress readout instead of printing a one-line summary.                                         |
| `e2e/search-progress.spec.ts` (new)                   | A real job watched to completion, a cancelled one, and the request count while it runs.                               |
| `CLAUDE.md`                                           | One line: progress backs off, stops at the end, and pauses in the background.                                         |

## Steps

1. **`search-state.ts`** (test first) — `isFinished(state)` for the four ends; `endingOf(search)`
   returning what happened in the UI's terms, including `expired` for a job the server discarded,
   which is not a failure and says so; `progressOf(search)` normalizing the fields the API may omit
   (percent, scanned, matched) and carrying the flag that says the match count is itself an estimate.
2. **`poll-interval.ts`** (test first) — attempt zero is 500 ms, each one doubles, ceiling 5 s. A job
   in this capture finishes inside a few of those; a real one would settle at the ceiling.
3. **`use-search.ts`** — add `refetchInterval` computed from the attempt count and the current state:
   a number while queued or running, `false` once finished. `refetchIntervalInBackground: false` so a
   hidden tab asks nothing. A 410 marks the job expired rather than erroring: the query's failure is
   translated into an end state, so the screen explains it and stops.
4. **`use-cancel-search.ts`** — a mutation over the existing delete handler that, on success, marks
   the job cancelled in the cache so the screen updates without waiting for another poll.
5. **`search-progress.tsx`** — while the first read is in flight: "starting". While running: the state,
   a percentage bar, scanned out of the estimated total, matched so far with the estimate marker when
   the server sets it, and a stop control. When it ends: done with what it matched, failed with the
   server's reason, cancelled, or discarded with an invitation to run it again. A failed refresh shows
   inline without stopping the polling.
6. **`run-control.tsx`** — replace the one-line job summary with the readout; the control keeps the
   button, the refusals and the warnings.
7. **Tests** — unit for the two pure modules, component tests for the readout, e2e for the real thing.
8. **`CLAUDE.md`** line.

## Risks

- **Polling that never stops.** An interval that keeps firing after the job ends is the classic version
  of this bug, and here it also keeps a finished job's slot alive. The interval is derived from the
  state, not from a timer the component owns, so an end state stops it by construction.
- **Polling too fast.** Identical GETs inside the same instant are scored (`http.get_dedupe`). Half a
  second is the floor, one query key per job, and no refetch on focus.
- **A job that expires under us.** Ten minutes without a read and the server discards it. Pausing in a
  hidden tab makes that more likely, which is precisely why the discarded case is a first-class ending
  rather than an error nobody can interpret.
- **Cancel racing the poll.** A cancel and an in-flight poll can land in either order; the mutation
  writes the cancelled state into the cache and the next poll is stopped by the end state, so the
  screen cannot flip back to "running".
- **Cancelling what is not ours.** Only a job this screen started may be stopped, the same rule the run
  control already follows for replacing one.
- **Sign-out mid-search.** The session ending cancels queries and clears the cache; nothing here may
  keep polling afterwards, and the shared expiry reaction already stops it.
- **Chaos.** Under `storm` a poll can fail; a failed poll is shown inline and the next one still
  happens, because giving up on one failure would leave the screen frozen mid-search.

## Verification

| #   | Acceptance criterion                        | How it is proven                                                                                                                                                                                                  |
| --- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Progress advances on its own                | Component test with two successive responses. E2E: a real job's percentage moves without interaction.                                                                                                             |
| 2   | The interval grows                          | Unit: the sequence and the ceiling. Component test: the scheduled delay increases between refreshes.                                                                                                              |
| 3   | Polling stops at an end state               | Component test with fake timers: no further request after `done`. E2E: request count stops climbing.                                                                                                              |
| 4   | A finished job reports what it matched      | Component test and E2E against a real finished job.                                                                                                                                                               |
| 5   | A failed job says why                       | Component test with a failed job carrying a reason.                                                                                                                                                               |
| 6   | A discarded job differs from a failed one   | Component test with a 410: the wording invites running it again and is not an error state.                                                                                                                        |
| 7   | The person can stop a search                | Component test: the stop control issues the delete and the state becomes cancelled. E2E: same, for real.                                                                                                          |
| 8   | An estimated count is marked                | Component test with `matched_is_estimate` set.                                                                                                                                                                    |
| 9   | A failed refresh does not stop the watching | Component test: one failing poll, then a successful one, with the failure shown in between.                                                                                                                       |
| 10  | Nothing is asked without a job              | Component test: no request when there is no id. E2E: the search screen before starting makes none.                                                                                                                |
| —   | Nothing else regressed                      | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL — `http.get_dedupe` and `search.abandoned` in particular. |
