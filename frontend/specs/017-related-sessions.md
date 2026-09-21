# 017 — Related sessions

## Context

An investigation is never one session. The screen now shows a session in full — what it is, what was
exchanged, how its traffic moved — and then stops: to see what else happened around it, a reader has
to go back to the search form and rebuild a query by hand, guessing the window and the endpoints.

The server already answers this question. Asked about a session, it returns the sessions it considers
related within a window around it, as a page of ordinary session rows, with a cursor when there are
more. In this capture that list is small and pointed: for a bare TCP session it comes back with the
handful of other connections between the same two machines, minutes apart — the shape of a host
working its way along a neighbour. That is the thread an investigator follows, and it is one click
away from being useful.

The server does not say _why_ it considers two sessions related, and it will not accept an arbitrary
window: three widths, and nothing else. Both of those constrain what this screen may claim and what
it may ask for.

## Goals / Non-goals

**Goals**

- From a session, see the sessions the server considers related to it, and open any of them.
- Let the reader widen or narrow the window among the widths the server offers.
- Read the rest of the page when there are more related sessions than the first page holds.
- Say nothing about why two sessions are related, because the server does not say.

**Non-goals**

- Our own notion of relatedness, or any filtering, sorting or grouping of the list.
- A graph or any visual of the relationships.
- Turning the list into a search, or carrying it into the results table.
- Changing what the search screen does.

## Requirements

- The session screen lists the sessions the server relates to this one: for each, when it happened,
  its protocol, its two endpoints, how much it carried and how risky the server thinks it is.
- Every entry opens that session at its own address, and the address is the one the server gave —
  identifiers are never re-typed as numbers.
- The reader can change the window among the widths the server accepts; the interface never asks for
  a width it would refuse.
- When the server says there are more, the reader can read on; each further page is asked for with
  the marker the server handed back, unchanged, and a marker is never reused across windows.
- A window with nothing in it says there is nothing around this session rather than showing an empty
  frame; while it loads, the screen says so and the rest of the session stays usable; a failure
  explains itself and offers one retry without taking the rest of the page down.
- The list is short by default and reachable by keyboard, like the rest of the screen.
- Reading the list costs one request per session and window, not one per redraw; going back to a
  window already read asks for nothing.

## Acceptance criteria

1. A session screen lists the sessions the server relates to it, with their time, protocol,
   endpoints, size and risk — current: NO → expected: YES.
2. Opening an entry lands on that session, at exactly the identifier the server gave — current: NO →
   expected: YES.
3. Changing the window re-reads the list, and every width sent is one the server accepts — current:
   NO → expected: YES.
4. When the server offers more, reading on asks with its own marker, unchanged, and appends to the
   list — current: NO → expected: YES.
5. A window with no related sessions says so, and does not look like a failure — current: NO →
   expected: YES.
6. A failure to read the list leaves the rest of the session on screen and offers a retry — current:
   NO → expected: YES.
7. Returning to a window already read sends no request — current: NO → expected: YES.
8. Nothing in the list claims a reason for the relationship — current: NO → expected: YES.
9. The backend's verdict stays clean while the list is used: no refused window, no marker replayed
   where it does not belong, no request repeated — current: unknown → expected: YES.

## Open questions

- Whether the chosen window belongs in the address, so a related list can be shared as it was seen.
  The search query is in the address because a search is the unit of work; this is a look around from
  a session. Proposed: keep it local to the screen, and leave the address naming the session only.
- Whether these rows should use the column set the server publishes for tables, or a fixed compact
  line. Proposed: a compact line — this is a short list beside a session, not a table to scan, and the
  published set is wider than the space.
