# 011 — Following a running search

## Context

A search now starts, and the screen says so once — then nothing. The job goes on scanning on the
server, and the person watching has no way to tell whether it is nearly done, stuck, or already
finished. That is the wrong state to leave someone in when the task's whole premise is a long search
that runs somewhere else.

The API reports on a running job in useful detail: how much of the window it has scanned, how many
sessions have matched so far and whether that number is itself an estimate, a percentage, and the
state it is in. Two of those states are ends nobody should have to guess at — a job can fail, and a
job can be cancelled.

Two rules shape how this must be done. The API discards a job nobody has asked about for ten minutes
and frees its slot, so following it is also what keeps it alive while someone is watching. And asking
too eagerly is its own problem: the backend counts identical requests made within the same instant,
and a progress display that asks every frame would be both useless and scored against us. Asking
slower as a job runs longer is the honest compromise.

## Goals / Non-goals

**Goals**

- While a search runs, the person can see how far it has got and how much it has found.
- Every way a job can end — finished, failed, cancelled, discarded for being unwatched — is visible
  and distinguishable.
- Watching stops when there is nothing left to watch, rather than asking forever.
- A running search can be stopped by the person who started it, and the slot freed.

**Non-goals**

- No reading the rows; the table is the next item.
- No history of finished searches, no list of what else is running.
- No notifications when a job finishes while the person is elsewhere.
- No streaming or live events — the API offers them for detections, not for search progress.

## Requirements

- While a job is queued or running, the screen reports its progress and refreshes it on its own.
- Refreshing slows down as the job goes on, so a long search does not produce a request per second
  for minutes.
- Refreshing stops as soon as the job reaches an end state, and does not resume by itself.
- A finished job says so and reports what it found; a failed one says it failed and why, if the server
  said; a cancelled one says it was cancelled.
- A job discarded for being unwatched is reported as such, distinctly from a failure, since the person
  can simply run it again.
- The person can stop a running search, and the screen then shows it as cancelled rather than as an
  error.
- Numbers that the server marks as estimates are shown as estimates, not as final counts.
- While the first report is still being fetched, the screen says the search is starting rather than
  showing an empty progress bar.
- A failure to read progress does not kill the search or the screen: it is reported, and reading
  resumes.
- Nothing is asked about a job once the session is gone, and nothing is asked at all when no job has
  been started.

## Acceptance criteria

1. A running job shows progress that advances without the person doing anything → current: NO →
   expected: YES.
2. The interval between refreshes grows as the job runs → current: NO → expected: YES.
3. Refreshing stops once the job is done, failed or cancelled → current: NO → expected: YES.
4. A finished job reports what it matched → current: NO → expected: YES.
5. A failed job says so, with the server's reason when there is one → current: NO → expected: YES.
6. A discarded job is distinguishable from a failed one → current: NO → expected: YES.
7. The person can stop a running search and sees it as cancelled → current: NO → expected: YES.
8. An estimated match count is labelled as one → current: NO → expected: YES.
9. A failed refresh is reported and refreshing continues → current: NO → expected: YES.
10. No progress request is made when no search has been started → current: NO → expected: YES.

## Open questions

1. **How slow should it get?** A job in this capture finishes in seconds, so a short interval feels
   right; the same code facing a real capture would be asking for minutes. The ceiling matters more
   than the floor.
2. **What happens when the person leaves the screen while a job runs?** Stopping the watching frees
   nothing on the server but risks the job being discarded as unwatched; keeping it costs requests for
   a screen nobody is looking at.
3. **Should a finished search keep being confirmed?** Once done, its rows can still be read, and the
   ten-minute idle rule applies to the whole job. Nothing needs refreshing, but going completely quiet
   means a job can expire under the reader's feet while they page through results.
