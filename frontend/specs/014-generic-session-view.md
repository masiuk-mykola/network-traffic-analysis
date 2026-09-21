# 014 — The generic session view

## Context

A result row already leads to a session's own address, but that screen is a placeholder: it prints
the id and nothing else. The handed-over task asks for one session in full — the decoded transaction
laid out so it can actually be read — and for the compromised machine to be reported with a link to
the spot in the interface where it shows. Neither is possible until this screen exists.

The server decodes each session and publishes, per protocol, what its fields are called, in what
order they belong, and what kind of value each one holds. Two things make a hand-written layout the
wrong answer. Capture points run different decoder generations, so the same protocol arrives in two
different shapes — a field that is a list in one is a single value in the other, a number in one is a
string in the other. And the decoded payload carries more than the published description mentions,
while the description in turn names fields a given session simply does not have.

This step is the generic view: built from the description, honest about the parts that do not match
it. One protocol gets a properly written layout in the next step.

## Goals / Non-goals

**Goals**

- A session opens at its own address, from a link or pasted cold, and shows what it is.
- A summary a reader can take in at a glance: when, where, between whom, how much, how risky.
- The decoded transaction rendered from the published description — its labels, its order, its
  value kinds — including repeated values.
- Nothing decoded is silently dropped, and nothing described but absent is faked.

**Non-goals**

- A hand-crafted layout for any one protocol; the timeline; related sessions; downloads.
- Editing, tagging or annotating a session.
- Re-deriving risk, or explaining a detection beyond what the server says.

## Requirements

- The screen states the session's identity: the moment it started and how long it lasted, the
  capture point, the protocol and transport, both endpoints, bytes and packets, and the risk with
  its band and the reasons the server gives. Times are UTC, and identifiers are shown exactly as
  they arrive — they are wider than a number and must never be re-typed as one.
- The decoded transaction is presented field by field in the order the server publishes, under the
  labels it publishes, formatted according to the kind of value it declares. A kind this app has
  never seen renders as plain text rather than breaking the screen.
- A described field that is repeated shows each of its occurrences; a described field this session
  does not carry is left out rather than shown as empty.
- Anything decoded that the description does not mention is still shown, plainly marked as not being
  part of the published description, so a reader of a session from an older decoder is not left
  looking at a screen missing half the transaction.
- A field the server marks as sensitive is visibly marked as such.
- Detections, carved files and whether the raw capture is still held are stated as facts, with no
  action attached yet.
- The screen carries a way back to the results it was opened from.
- While it loads there is a loading state; when the id names no session the screen says so plainly
  rather than showing an error; a failure to read offers a retry; a session with nothing decoded
  says that instead of showing an empty frame.

## Acceptance criteria

1. Opening a session's address shows its summary — start, capture point, protocol, endpoints, bytes
   and risk — current: NO → expected: YES.
2. The transaction's fields appear with the labels and in the order the server publishes for that
   protocol — current: NO → expected: YES.
3. A session decoded by the older generation shows its values too, including the ones whose shape
   the description does not match — current: NO → expected: YES.
4. A decoded field the description never mentions is visible and marked as undescribed — current: NO
   → expected: YES.
5. An address naming no session says so, without an error screen and without a retry loop —
   current: NO → expected: YES.
6. A session with no decoded transaction says so instead of rendering an empty section — current: NO
   → expected: YES.
7. Nothing on this screen parses a session id as a number: the id shown and linked is exactly the
   one the server gave — current: unknown → expected: YES.
8. The backend's verdict stays clean while the screen is used: the session and its description are
   each read once per visit, and nothing is retried blindly — current: unknown → expected: YES.

## Open questions

- What marking a field as sensitive is meant to do beyond labelling it — the contract carries the
  flag but does not say whether the value is expected to be hidden by default. Proposed: mark it,
  show it, and revisit if the task says otherwise.
- Whether the older decoder's values should be reconciled to the published description (so that a
  differently shaped field lands under its proper label) or shown as undescribed. Proposed: show
  them as undescribed rather than guessing a mapping the server does not publish.
