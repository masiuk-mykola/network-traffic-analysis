# 012 — The results table

## Context

Everything so far has been preparation: a query, an estimate, a job, and a progress bar. What the task
actually asks for is the thing at the end of it — a table of sessions that is comfortable to scan,
with a lot of rows in it. This is the screen the work is judged on.

The API hands those rows over in a way that shapes the interface. They arrive in pages behind an
opaque cursor, in scan order, and they start arriving **while the search is still running**: a page
can come back with no cursor and a flag saying "not finished" — meaning caught up, ask again later —
or with a flag saying that was the end. Page size is capped at five hundred, and the server tells you
what it actually applied. Asking for a different order needs a finished search; asking earlier is
refused.

The columns are published too, with their types, their default visibility, their widths and which of
them can be sorted on. Notably, the live server publishes a column whose type is not in its own
documented list — and the documentation says plainly to render anything unknown as text. An interface
that hard-codes a column set, or assumes it knows every type, breaks on contact with the real server.

## Goals / Non-goals

**Goals**

- The sessions a search matched are shown in a table that stays usable at thousands of rows.
- Rows appear while the search is still running, and keep appearing until it is done.
- The table is built from the columns the server publishes, including ones it has not documented.
- A row leads to the session it represents.
- Every state is covered: nothing yet, nothing at all, more coming, that was everything, and failure.

**Non-goals**

- No sorting yet if the server will not accept it — see the open questions.
- No column chooser, no saved layouts, no resizing.
- No export, no bulk selection, no actions on rows beyond opening one.
- No session detail; the next phase.

## Requirements

- Rows from the current search are shown as soon as the first page arrives, without waiting for the
  search to finish.
- More rows are asked for only when the person needs them, or when the search has produced more since
  the last look — never in a loop that asks continuously.
- The cursor the server returned is sent back exactly as received; nothing is rebuilt or guessed.
- No more rows are asked for per page than the server accepts, and the size the server says it applied
  is what the interface assumes.
- Scrolling stays smooth with thousands of rows in the table.
- The columns, their order, their default visibility and their widths come from the server; a column
  whose type the interface does not recognise is shown as plain text rather than omitted or broken.
- While the search runs and no rows have matched yet, the table says it is still looking — not that
  there is nothing.
- When the search has finished with nothing, the table says so and suggests widening the query.
- When the last page has been read, the table says that is everything, rather than looking like it is
  still loading.
- A failure to read a page is reported without losing the rows already shown, and can be retried.
- Selecting a row opens that session.
- Nothing is asked for when there is no search, and nothing keeps asking after the session has ended.

## Acceptance criteria

1. Rows appear while the search is still running → current: NO → expected: YES.
2. More rows load when the person reaches the end of what is shown → current: NO → expected: YES.
3. The cursor is sent back byte for byte → current: NO → expected: YES.
4. No page is requested larger than the server allows → current: NO → expected: YES.
5. The table renders thousands of rows without becoming unusable → current: NO → expected: YES.
6. The columns match what the server publishes, including the undocumented type, which renders as text
   → current: NO → expected: YES.
7. "Still looking" and "nothing matched" are different states on screen → current: NO → expected: YES.
8. Reaching the end says so → current: NO → expected: YES.
9. A failed page keeps the rows already shown and offers a retry → current: NO → expected: YES.
10. Selecting a row opens that session → current: NO → expected: YES.
11. No results are requested when no search has been started → current: NO → expected: YES.

## Open questions

1. **What happens when the search is still running and the reader reaches the end of what exists?**
   The API distinguishes "caught up, more may come" from "that was everything". The first could show a
   quiet "waiting for more", or could poll gently, or could ask the person to press for more. Polling
   is the most alive and the most expensive.
2. **Do we offer sorting at all in this item?** The server refuses a different order until the search
   is finished, so the control would be disabled for exactly as long as the interesting part lasts,
   then become available. Offering it and explaining the wait is honest; hiding it until done is
   simpler.
3. **How is "comfortable to scan" measured here?** The task says the table has to be comfortable with a
   lot of rows, which suggests windowing. That adds a dependency and complexity; a capped page count
   with explicit paging is simpler but scrolls worse.
