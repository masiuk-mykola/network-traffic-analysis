# 013 — Make results linkable

## Context

The search screen already keeps the query and the job it started in the address bar, so a reload
returns to the same search rather than to an empty form. Two things are still missing before a
result can be handed to someone else.

First, the order of the rows is not part of that address. The column headers the server marks as
sortable render a control, but the control does nothing: the order is whatever the search was
created with, and it cannot be changed or shared. The server sorts for us and only accepts an order
once the job has finished — so this is a server-side re-read, not a client-side reshuffle of the
rows already loaded.

Second, the handed-over task asks for the compromised machine to be reported **with a link to that
spot in the interface**. That is only possible if a search, its order, and a single session are all
addressable.

## Goals / Non-goals

**Goals**

- The chosen order is part of the address, alongside the query and the job.
- A finished search can be re-ordered on the server by the columns the server says are sortable.
- A row opens that one session at its own address, and that address survives being shared.
- Opening a shared address restores what it describes, or explains plainly why it cannot.

**Non-goals**

- Multi-column ordering, or ordering by a column the server does not publish as sortable.
- Re-ordering a running search, or sorting the loaded rows in the browser.
- Column choosing, widths or saved layouts.
- The session screen itself — this change only makes it reachable and addressable.

## Requirements

- The order is chosen from the columns the server publishes as sortable, in both directions, with
  the current one visible in the header. The default is the order the search was created with.
- While the job runs, the order cannot be changed and the controls say why; it becomes available the
  moment the job finishes.
- Changing the order re-reads the results from the beginning in the new order, keeps the same job —
  it never starts a second search — and shows that it is re-reading rather than leaving stale rows
  that no longer match the header.
- The address carries the query, the job and the order together. Restoring from it shows the same
  rows in the same order without starting anything new.
- A row leads to that session's own address. Returning from it shows the same search, order and rows
  again, without re-running the search.
- An address naming a job the server no longer has, or one this account may not read, explains that
  in words and offers to run the query it still carries; it is not a dead error screen.
- The states already in place for the table — loading, still-looking, nothing matched, a failed page
  with a retry — also cover the re-read after an order change.

## Acceptance criteria

1. Choosing a sortable column on a finished search changes the order of the rows and the address
   reflects it — current: NO → expected: YES.
2. Opening that address in a fresh tab shows the same rows in the same order, and no new search is
   started — current: NO → expected: YES.
3. The order controls are unavailable while the job runs and become available when it finishes, with
   the reason stated — current: partly (inert controls, no reason) → expected: YES.
4. Changing the order re-reads from the first page; no row from the previous order survives the
   change — current: NO → expected: YES.
5. Opening a row's address shows that session, and going back shows the same search and order —
   current: NO → expected: YES.
6. An address naming a job that no longer exists explains it and offers to run the query again —
   current: NO → expected: YES.
7. The backend's verdict stays clean through all of the above: no duplicate jobs, no order asked of
   a running search, cursors returned untouched — current: unknown → expected: YES.

## Open questions

- What the server answers when an order is asked of a job that is still running, and when a job id
  belongs to another account — the contract says the order is accepted "only once the search is
  done" but does not spell out either refusal. To be confirmed against the running server at plan
  time, not guessed.
- Whether returning from a session should restore the scroll position in the table, or only the
  rows. Not required by the task; currently proposed as out of scope.
