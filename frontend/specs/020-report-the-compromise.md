# 020 — Report the compromise

## Context

The handed-over task ends with a question the interface exists to answer: one machine on this network
is compromised, no ready-made rule names it, and the finder is asked to say **where it started**, to
link to that spot in their own interface, and to say briefly how they found it and what they ruled
out. It also warns that the capture contains things that look suspicious and are not, and that the
answer must be found through the interface rather than by reading the backend.

Everything needed for that is now built: a query over capture points and a window, conditions from
the published fields, a results table sorted by risk, a session in full with its decoded transaction,
its traffic over time, and the sessions the server relates to it. What is missing is the use of it —
and the write-up, which is part of what was asked for and does not exist yet. The project's own
README is still the one the framework generated.

One constraint on the write-up comes from the interface itself: a started search is a job that
belongs to one account and the server discards it when nobody reads it, so a link naming a job is
worthless to a reader tomorrow. A link to a session, or to a query that the reader can run, survives.

## Goals / Non-goals

**Goals**

- Name the compromised machine and say when and how its activity begins.
- Anchor that claim with links into this interface that still work for someone opening them fresh.
- Say how it was found: what was looked at, in what order, and what made it stand out.
- Say what was ruled out, and why those things are noise rather than the answer.
- Reach the conclusion using only what the interface shows.

**Non-goals**

- Reading the backend's source, its fixtures or its seed to obtain or confirm the answer.
- Building new interface features for the investigation; if something is missing, that is a finding
  about the interface, recorded as such.
- A full incident report, a timeline of every session, or attribution beyond what the capture shows.
- The rest of the project's documentation, which is a separate step.

## Requirements

- The write-up names one machine, identifies it the way the capture identifies it, and states when
  its suspicious activity first appears.
- It carries at least one link into the interface that opens the evidence directly, and those links
  work from a cold start — for a reader who signs in and follows them, with no search job of ours
  alive on the server.
- It explains the path taken in a few sentences: where the investigation started, what narrowed it,
  and which screen made the answer visible.
- It names at least one thing that looked suspicious and was dismissed, with the reason.
- It distinguishes what the server asserts from what the reader concludes: where the server itself
  flags something, that is quoted; where the conclusion is ours, it is marked as ours.
- Every claim in it can be re-checked by following the links; nothing rests on data the interface
  does not show.
- If the interface turns out to be missing something the investigation needed, that gap is written
  down rather than worked around silently.

## Acceptance criteria

1. The project's README names the compromised machine and when its activity starts — current: NO →
   expected: YES.
2. It links into this interface, and each link opens the evidence for a reader who has just signed in
   — current: NO → expected: YES.
3. It states how the machine was found, in a few sentences — current: NO → expected: YES.
4. It names something suspicious that was ruled out, and why — current: NO → expected: YES.
5. Every statement in it is supported by something the interface displays — current: NO → expected:
   YES.
6. Nothing in it depends on a search job that will expire, or on any other state that is ours and
   temporary — current: NO → expected: YES.
7. The investigation itself is conducted through the interface, with the backend's own sources left
   unread for this purpose — current: NO → expected: YES.

## Open questions

- Whether the write-up belongs in the project's README or in a document of its own that the README
  points to. Proposed: in the README, as the task asks, kept short enough to read in place.
- Whether a reader is expected to reproduce the search themselves or to be handed a link that shows
  the evidence without running anything. Proposed: both — a session link that stands alone, and a
  query link they can run to see the pattern.
