# 007 — The query form

## Context

The main screen of this task is a search, and a search here is a job on the server: you say which
capture points and which slice of time, the server goes away and works, and results arrive page by
page. Everything else on that screen — conditions, progress, a table of results — hangs off the two
choices made first. This item builds those two, and with them the first screen that reads real data
instead of standing in for one.

Both choices have teeth. The API accepts between one and five capture points and refuses the rest, so
"all of them" is not a default that can be assumed. And the window is not free: the points do not all
see the same traffic, one of them runs minutes behind the others, and the data itself covers a few
days — a window picked from today's date lands on nothing at all, which looks exactly like a broken
app.

The points are also the first place the two accounts differ: one of them may read fewer of them than
the other. So the form cannot present a fixed list; it has to show what this account can actually
search, and say so when that is less than everything.

## Goals / Non-goals

**Goals**

- A person picks capture points and a time window, and can see what those choices mean before running
  anything.
- The form only offers what this account may read, and what the API will accept.
- A window that cannot return anything is caught before a search is started.
- The screen behaves while the list of points is loading, when the account can read none, and when the
  list cannot be fetched.

**Non-goals**

- No conditions on fields yet, no estimate of how much a search would cost, no starting a search — the
  next three items.
- No saved or recent queries.
- No sharing the query through the address bar; that comes with the results.
- No presentation of per-point detail beyond what choosing between them requires.

## Requirements

- The form offers exactly the capture points this account may read, each identified well enough to
  tell apart: its name, where it is, and whether it is keeping up.
- At least one point must be chosen and no more than the API accepts; both limits are explained in
  place rather than only when the server refuses.
- A point that is behind on traffic is visibly marked, because a window near "now" will miss what it
  has not reported yet.
- The window is chosen as a start and an end; the end cannot be before the start, and neither may be
  empty.
- The window offered by default lands on traffic that exists, rather than on an empty stretch of time.
- The window states which zone it is in, matching how times are shown everywhere else.
- While the points are loading, the form shows that and cannot be submitted.
- If the account may read no points, the screen says so plainly instead of showing an empty picker.
- If the list cannot be fetched, the screen offers to try again and does not pretend there are no
  points.
- Choices survive a reload of the screen, so a mistake in a later step does not cost the setup.

## Acceptance criteria

1. The picker lists exactly the points the signed-in account may read → current: NO → expected: YES.
2. Submitting with no point chosen is refused in place, with a reason → current: NO → expected: YES.
3. Choosing more points than the API accepts is refused in place → current: NO → expected: YES.
4. A point that is behind is marked as such → current: NO → expected: YES.
5. An end before the start is refused in place → current: NO → expected: YES.
6. The default window covers time that actually has traffic → current: NO → expected: YES.
7. While the points load, the form cannot be submitted → current: NO → expected: YES.
8. When the list fails to load, the screen offers a retry rather than an empty picker → current: NO →
   expected: YES.
9. Reloading the screen keeps the choices → current: NO → expected: YES.

## Open questions

1. **Where does the default window come from?** Each point reports when it last saw traffic, so the
   form could end the window there and open it some hours earlier. That is accurate but surprising the
   first time — the window will not say "today". The alternative is a fixed recent range, which is
   predictable and often empty.
2. **How are the points presented?** A short list with checkboxes is the obvious answer for three
   points and is wrong if this ever grows; a searchable multi-select is the opposite trade.
3. **Where do the choices survive?** The address bar makes them shareable and survives a reload, but
   the plan so far puts query state in the URL only once there are results to link to. The alternative
   is keeping them in the browser until then.
