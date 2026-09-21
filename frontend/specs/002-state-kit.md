# 002 — The state kit

## Context

Every screen this task asks for reads data that can be slow, empty, forbidden or broken, and the task
judges the interface on exactly that: what the user sees while a search is running, when there is
nothing, and when it fails. Right now there is nothing to render any of it with — the three routes are
placeholders, and the first real screen would have to invent its own spinner, its own "no results" and
its own error box. Three screens later we would have three different vocabularies for the same four
situations, and the one that matters most — a long-running server job — would be the least consistent.

The data layer already distinguishes these cases: a failure arriving in the UI carries the API's stable
code, the status and, when the server stated one, how long to wait before trying again. Nothing
consumes that yet. This item builds the small set of pieces that do, before any screen exists to copy
the wrong pattern from.

## Goals / Non-goals

**Goals**

- One shared way to show: work in progress, nothing to show, a failure the user can retry, and a
  failure the user cannot act on.
- A failure presentation that turns what the data layer already knows — the kind of failure, and any
  wait the server asked for — into something a person can read and act on.
- Pieces that work both for a whole screen and for one region of it, since a page can have several
  independent reads.

**Non-goals**

- No data fetching, no new routes, no screen built out of these pieces yet.
- No design system, no theming decisions beyond what the project already uses.
- No animation work beyond what is needed for a progress indicator not to flicker.
- No toast infrastructure or global notification queue — that is only worth building when something
  needs to survive a navigation.

## Requirements

- While a read is in flight, the user sees that work is happening, in a way that keeps the surrounding
  layout from jumping when the content arrives.
- A read that finishes with nothing shows a short statement of what is missing, distinguishable at a
  glance from a failure, and — when the emptiness is a consequence of the user's own choices — a way
  back to changing them.
- A failed read states what went wrong in the user's terms, not the server's, and offers a retry when
  retrying can plausibly help.
- A failure the user cannot fix by retrying — no permission to see this, or the session is gone — does
  not offer a retry, and says what to do instead.
- When the server stated how long to wait, the interface does not invite an immediate retry that will
  be refused; it says when it is worth trying again.
- Each piece can be used for a whole screen or for a single region, and reads correctly in both.
- Every piece is reachable and announced to assistive technology: progress is announced, a failure is
  announced, and a retry is a real focusable control.
- None of this leaks server internals — an upstream contract failure reads as a generic problem on our
  side, not as a schema dump.

## Acceptance criteria

1. A screen region waiting for data announces progress to a screen reader → current: NO → expected: YES.
2. A read that returns nothing shows an empty state that is visually and semantically distinct from a
   failure → current: NO → expected: YES.
3. A retryable failure shows a retry control that re-runs the read → current: NO → expected: YES.
4. A permission failure and a gone session show no retry control → current: NO → expected: YES.
5. A failure carrying a stated wait shows that wait instead of an immediate retry → current: NO →
   expected: YES.
6. A failure whose cause is ours (an unexpected response from the API) reads as a generic problem and
   exposes no server detail → current: NO → expected: YES.
7. The same piece renders correctly as a full-screen state and inside a card-sized region → current:
   NO → expected: YES.
8. Reverting any of the above turns at least one test red → current: NO → expected: YES.

## Open questions

1. The API can refuse a request for reasons the user could fix by changing the request (a window too
   wide, a filter the server rejects) rather than by retrying. Do those get their own presentation in
   this item, or do they wait until the search form exists and can point at the offending field?
2. Should a failure show the API's stable code somewhere discreet? It helps when reporting a problem
   and it is meaningless to most users; it is also the kind of thing a reviewer of this task might look
   for.
3. Does an empty state need an illustration or icon vocabulary now, or is text enough until the screens
   show what they actually need?
