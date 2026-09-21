# 009 — Sizing a search before running it

## Context

A search here is not free. The server allows three at a time per account, each one runs as a job, and
the window this capture covers holds about a hundred thousand sessions. So the first question anyone
building a query has is the one the interface cannot currently answer: is this going to come back with
four rows, or forty thousand?

The API answers it cheaply. It evaluates the filter on a sample of the window and scales the result,
and it says outright that the number is approximate. It also reports how much it would have to look
through to answer properly — which is the honest measure of what a real search would cost.

Getting this in before the search itself is worth doing in that order. Someone who can see that their
window matches nothing will fix the window instead of spending a slot to discover it, and someone
staring at a number in the tens of thousands will add a condition before asking for a table of them.

There is a limit worth respecting: the endpoint allows a handful of requests per second per session
and refuses the rest, and the backend scores how well the client stays inside that. A form that asked
on every keystroke would be both wasteful and scored against us.

## Goals / Non-goals

**Goals**

- While a query is being built, the person can see roughly how many sessions it would match.
- The number is clearly marked as an estimate, not a result.
- The cost of the search is visible alongside it, so "matches little but reads everything" is not a
  surprise.
- Asking costs at most what the API allows, no matter how fast someone types.

**Non-goals**

- No running the search; that is the next item.
- No history of previous estimates, no comparison between them.
- No charts or distribution over time; the API offers a histogram, and it belongs with the results.
- No blocking a search because the estimate is large — informing, not gatekeeping.

## Requirements

- An estimate appears for the current query once it is complete enough to run, and updates as the
  query changes.
- The estimate is never asked for while the query is unfinished: no capture point, a backwards window
  or an unfinished condition means nothing is sent.
- The number is presented as approximate, distinctly from anything exact.
- Alongside the match count, the person can see how much the server would have to read to answer for
  real.
- Rapid changes produce at most the rate the API permits; the interface waits for the query to settle
  rather than asking per change.
- While an estimate is being fetched, the previous one is not presented as current.
- An estimate of zero is stated plainly, because it is the most useful answer the screen can give
  before a search is spent.
- A failed estimate is not fatal: the rest of the form keeps working, the failure is visible and can be
  retried.
- If the server refuses because we asked too often, the interface waits out the period it states
  rather than retrying immediately.

## Acceptance criteria

1. A complete query shows an estimated match count → current: NO → expected: YES.
2. An incomplete query sends no estimate request → current: NO → expected: YES.
3. The number is labelled as an estimate → current: NO → expected: YES.
4. The scanned cost is shown next to the match count → current: NO → expected: YES.
5. Typing quickly through several changes produces no more requests than the API allows per second →
   current: NO → expected: YES.
6. While fetching, the old number is not shown as if it were current → current: NO → expected: YES.
7. A zero estimate says so plainly rather than looking empty → current: NO → expected: YES.
8. A failed estimate leaves the form usable and offers a retry → current: NO → expected: YES.
9. A refusal for asking too often is waited out rather than retried at once → current: NO → expected:
   YES.

## Open questions

1. **Does the estimate refresh on its own?** The capture is a fixed window in the past, so the answer
   will not drift while someone looks at it. Refreshing on an interval would be waste; refreshing only
   on change may leave a stale number visible after an error.
2. **Where does it sit?** Next to the run control is where the decision is made, but that is also the
   busiest part of the form. Above the conditions keeps it visible while they are edited.
3. **How approximate is "approximate"?** The API returns a plain integer and a flag. Rounding it for
   display ("about 12,000") reads as honest; showing "12,431" reads as precise and is not.
