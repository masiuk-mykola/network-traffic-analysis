# 010 — Starting a search

## Context

The form can describe a search and say roughly how big it would be. It cannot yet start one, which is
the point of the screen. Pressing the button is also where this interface stops reading and starts
creating, and the server has opinions about that.

A search is a job. Asking for one is answered immediately with a queued job rather than results, and
that job then runs on the server whether or not anyone is watching. Three of them may exist per
account at a time; a fourth is refused outright for a stated period. The server also invites the
client to label each request so that a retry after a failure returns the job already started instead
of a second, identical one — which matters because the failure worth retrying here is exactly the kind
that leaves you unsure whether the first attempt landed.

That combination is easy to get wrong in ways that are invisible locally and obvious in the server's
own bookkeeping: a double-click that spends two of three slots, a retry after a timeout that creates a
twin, a new search started while the old one still runs and is never cleaned up. The backend watches
for all three.

## Goals / Non-goals

**Goals**

- A finished query can be started, and the person immediately sees that it is running.
- Starting the same search twice — by double-click, by retry, by reload — produces one job, not two.
- A new search replaces the previous one cleanly, leaving no job running that nobody will read.
- The three limits the server imposes are visible and handled: refusal when out of slots, refusal
  while the server is busy, and anything the job itself warns about.

**Non-goals**

- No following the job's progress beyond the fact that it started — the next item.
- No reading results, no table.
- No cancelling from a list of running searches; only the one this screen started.
- No saved searches or history.

## Requirements

- Starting a search is possible only when the query is complete, by the same rules that already gate
  the estimate.
- Once started, the person sees that a search exists and is running, and the control cannot start a
  second one while the request is in flight.
- Two attempts at the same query, whether from a repeated press or a retry after a failure, result in
  one job on the server.
- Starting a new search while a previous one from this screen is still running ends the previous one
  first, so it does not sit there unread.
- Leaving the screen, or reloading it, does not leave a job running unnoticed: either the screen finds
  it again, or it is ended.
- When the server refuses because no slot is free, the person is told, and told when to try again, and
  not invited to retry sooner.
- When the server is momentarily unavailable, retrying is offered and a retry does not create a second
  job.
- Anything the job reports as a warning — a capture point that could not be read, a window partly
  outside retention — is surfaced rather than hidden behind a number.
- The started search is identified in the address bar, so a reload returns to it rather than to an
  empty form.

## Acceptance criteria

1. A complete query can be started and the screen shows it is running → current: NO → expected: YES.
2. The control cannot be pressed twice into two jobs → current: NO → expected: YES.
3. A retry after a failed attempt returns the job already started rather than creating another →
   current: NO → expected: YES.
4. Starting a second search ends the first → current: NO → expected: YES.
5. A refusal for want of a slot is explained, with the wait, and offers no immediate retry → current:
   NO → expected: YES.
6. A momentary server failure can be retried without creating a twin → current: NO → expected: YES.
7. Warnings the job reports are visible → current: NO → expected: YES.
8. Reloading after starting returns to the same search → current: NO → expected: YES.
9. No job started by this screen is left running when the screen moves on → current: unverified →
   expected: YES.

## Open questions

1. **What happens to a running search when someone edits the query?** Ending it immediately frees the
   slot but throws away work that may still be wanted; keeping it means the screen shows results for a
   query that no longer matches the form. Neither is obviously right.
2. **How long should the label that makes a retry safe stay valid?** The server keeps it for a while,
   so a repeat within that period returns the same job. A label that lives as long as the query means
   pressing again after an edit correctly starts a new search; one that lives longer would return a
   stale job.
3. **Should leaving the screen end the search?** The job survives on the server and could be picked
   back up from the address bar, which is useful. Leaving it running also consumes one of three slots
   for as long as it takes.
