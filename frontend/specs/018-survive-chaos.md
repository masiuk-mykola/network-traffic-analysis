# 018 — Survive an unreliable server

## Context

Everything built so far was built against a calm server. The capture API can be told to misbehave,
and two of its profiles are the ones that matter here: one where a fifth of reads are refused, a
twentieth of connections are dropped outright, answers take up to a second and a half, a search can
be refused before it starts or fail mid-scan; and one where the access token lives fifteen seconds,
so it expires under the reader's hands.

Driven through both, the app comes out unevenly. Under expiring tokens it is genuinely fine: nothing
failed, nothing surfaced, the renewal happened out of sight and a search ran to completion. Under the
storm it is not: the search screen and the session screen both collapse into a single full-page
"could not load this — try again", losing the form, the summary and everything else that had already
arrived, because one read of many failed. Pressing that retry repeatedly did not get the screen back.

That is the gap this step closes. A forensic tool is used in the middle of an incident, on
infrastructure that is itself having a bad day; a refused read is a normal event, not an occasion to
throw the screen away.

## Goals / Non-goals

**Goals**

- A failure takes down only the part of the screen that needed it, and says so where it happened.
- Transient refusals recover on their own within a few seconds, without the reader doing anything.
- Where a retry is offered, pressing it actually retries, and says it is doing so.
- A search the server refuses or fails is reported as an outcome, in the server's own words.
- Slowness reads as work in progress, never as an empty or finished screen.
- What already works under expiring tokens keeps working.

**Non-goals**

- Offline support, request queueing, or retrying writes on the reader's behalf.
- Surfacing the server's own component health (a separate step).
- Changing the retry policy's shape — the server's advertised delays are already honoured and must
  stay honoured.
- Tuning latency or adding skeleton animations for their own sake.

## Requirements

- When one read of a screen fails, the rest of that screen stays usable: the parts that did arrive
  are shown, and the failure is reported next to the part that is missing.
- A refusal the server marks as temporary is retried automatically, within the delay it advertises,
  and the reader sees that something is being re-attempted rather than a dead end.
- A retry control re-attempts the read it belongs to and reports the new outcome — including a second
  failure, which must not leave the control looking as though nothing happened.
- A connection that is dropped is treated as a temporary failure, the same as a refusal.
- A search refused before it starts waits out the advertised delay and can then be started again; a
  search the server fails during its scan is shown as failed, with whatever reason the server gives,
  and the screen stays usable.
- A slow answer keeps its loading state on screen for as long as it takes; nothing shows an empty
  result while a read is still in flight.
- An expired access token is never visible to the reader: no screen bounces to sign-in, no failure is
  reported, and nothing is asked twice because of it.
- Nothing about any of this changes what the server scores: no request is repeated faster than the
  delay it was given, no refused request is retried blindly, and no read is duplicated.

## Acceptance criteria

1. With a fifth of reads refused, the search screen keeps its form and reports the failure only where
   it happened — current: NO (the whole screen becomes one retry) → expected: YES.
2. With a fifth of reads refused, a session screen still shows what arrived, each missing part saying
   so on its own — current: partly (the timeline and the neighbours already do; the summary does not)
   → expected: YES.
3. A read refused once recovers without the reader pressing anything — current: unknown → expected:
   YES.
4. Pressing a retry that fails again shows the new failure rather than silence — current: NO →
   expected: YES.
5. A dropped connection behaves like a refusal, not like a crash — current: unknown → expected: YES.
6. A search refused for want of capacity can be started again once the advertised delay has passed —
   current: YES → expected: YES (must not regress).
7. A search the server fails mid-scan is reported as failed with the server's reason — current:
   unknown → expected: YES.
8. Under fifteen-second access tokens, a full pass over sign-in, search and a session shows no
   failure and no bounce to sign-in — current: YES → expected: YES (must not regress).
9. The backend's verdict stays clean under both profiles — current: unknown → expected: YES.

## Open questions

- Whether the server's own report that a component is degraded (the storm marks its session index as
  rebuilding) should be shown to the reader. Proposed: out of scope here, and worth its own step,
  because it is a status surface rather than a failure path.
- How long "recovers on its own" may take before it should say something to the reader. Proposed:
  keep the delays the server advertises and make the attempt visible, rather than inventing a budget
  of our own.
