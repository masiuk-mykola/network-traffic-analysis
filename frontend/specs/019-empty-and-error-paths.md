# 019 — Finish the empty and error paths

## Context

The failure paths were hardened in the previous step: a refused read now costs the part of the screen
that needed it, and a retry says it is retrying. What is left are the gaps that only show up on
particular data or with a particular account.

Three of them are real and checked against the running server.

The two demo roles do **not** differ in what they may do — the observer signs in, searches, reads
sessions, their traffic and their neighbours, exactly as the analyst does. They differ in what the
data contains: for an observer the server replaces sensitive values with a marker, and says so in its
own contract. The same HTTP session shows the analyst a cookie and the observer a redaction. Our
screens do not know about it, so that marker is rendered as raw content — the reader is shown a
little piece of JSON where a value should be.

Second, one reading surface still has no failure state at all: the list of values a closed field
offers, behind a condition. When that read fails, the control simply never fills, with no explanation
and no way to try again.

Third, the server reports the health of its own parts, and under load it says so plainly — the
session index rebuilding, searches likely to be slow or to fail. Nothing in the interface asks, so a
reader whose searches are crawling has no way to know it is not their query. That read is also the
one the server scores for politeness, so it may not be asked for often.

## Goals / Non-goals

**Goals**

- A value withheld because of the reader's role reads as withheld, in words, and says why.
- Every surface that reads something has all four of its states, including the one that does not.
- What the server says about its own health is visible when it is not well, in the server's words.
- An empty answer never looks like a failure, and a failure never looks like an empty answer.

**Non-goals**

- Inventing a permissions model the API does not have: no "no access" screens for things both roles
  may do.
- A status page, a history of incidents, or per-component detail beyond what the server states.
- Changing the retry policy, the redaction itself, or what the server chooses to withhold.
- Re-styling states that already work.

## Requirements

- Where the server has withheld a value for this reader's role, the interface says it is withheld and
  that the role is the reason, and shows nothing of the value itself — including inside a repeated
  field, and inside the transaction view of a protocol that has one.
- The reader's own role is visible while they are looking at a session, so a withheld value is not a
  mystery.
- A closed field's list of values has a loading state, a failure with a retry, and a sensible fallback
  when the list cannot be read at all, so a condition can still be written by hand.
- When the server reports any part of itself as degraded, the interface says so once, prominently,
  quoting the server's own explanation, and stops saying it when the server recovers.
- That health question is asked rarely — no more often than the server's own limit — and not at all
  while the tab is in the background.
- Every reading surface distinguishes: still loading, nothing there, and failed. A surface that shows
  nothing must say which of the three it means.
- None of this adds a request to a screen that did not need one, and nothing is asked twice.

## Acceptance criteria

1. An observer reading a session sees the withheld values described as withheld, with the role given
   as the reason, and none of the underlying data — current: NO (a raw marker is printed) → expected:
   YES.
2. An analyst reading the same session sees the values themselves — current: YES → expected: YES
   (must not regress).
3. The reader's role is visible on a session screen — current: partly (only in the header) →
   expected: YES.
4. A failed read of a closed field's values reports itself and offers a retry, and a condition can
   still be completed without that list — current: NO → expected: YES.
5. While the server reports a degraded part, the interface shows the server's explanation; when the
   server is well again, it does not — current: NO → expected: YES.
6. The health question is asked no more often than the server's limit, and not while the tab is
   hidden — current: not asked at all → expected: YES.
7. No screen shows an unexplained blank: each empty surface says whether it is loading, empty or
   failed — current: partly → expected: YES.
8. The backend's verdict stays clean, including the check that grades how often health is asked —
   current: unknown for the new read → expected: YES.

## Open questions

- Where the degraded notice belongs: alongside the screens' own content, or once at the top of the
  application. Proposed: once at the top, since it is about the server rather than about any screen.
- Whether a withheld value should be marked field by field or summarised once per session. Proposed:
  field by field, where the reader is looking, with the summary left to the role already shown in the
  header.
