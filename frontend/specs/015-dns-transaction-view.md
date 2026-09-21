# 015 — A first-class DNS view

## Context

Every session now renders from the server's own description of its protocol: a flat list of label
and value. That is the right floor for eight protocols, but it does not read as a transaction. A DNS
exchange is a question and an answer, and the generic list shows them as twenty-odd unrelated rows —
the query name three rows above the response code, the answers below a row called
`dns.answers[].ttl`.

The handed-over task asks for exactly this: one protocol written properly, laid out so the
transaction can actually be read, with the anomalies visible. DNS is the protocol with the richest
published description here, and it is where the interesting traffic is: the riskiest sessions in
this capture are bursts of no-such-name answers for machine-looking host names, which the server
itself flags as a known technique. A reader who cannot see the question next to its answer cannot
see that pattern.

Both decoder generations are in this capture and they disagree about shape: one gives the response
code as a named pair, the other as a bare number; one gives authority records as a list, the other
as a single record; one quotes numbers as numbers, the other as strings. A layout that reads only
the canonical shape would show a blank screen for a third of the capture.

## Goals / Non-goals

**Goals**

- A DNS session reads as one exchange: what was asked, what came back, and what that means.
- Both decoder generations render, with the same meaning, from whichever shape they arrive in.
- What the server already says about the risk is visible against the transaction, not buried.
- Values a reader takes elsewhere — the query name, an address, an identifier — can be copied.

**Non-goals**

- A layout for any other protocol; those keep the generic view.
- Judging a session ourselves, or inventing anomalies the server has not named.
- Cross-session analysis (the burst, the timeline, related sessions) — that is elsewhere.
- Editing, exporting or downloading anything.

## Requirements

- A DNS session shows the question and the answer as two halves of one exchange: the name asked, its
  type and class, and against it the response code, the answers with their record type, time to live
  and data, and any authority or additional records.
- The response code is shown by name whichever way it arrives; a code with no known name is shown as
  the number it is, not hidden.
- The flags are stated as the ones that are set, in words, rather than as a list of true and false.
- Records arrive as a list or as a single record depending on the decoder; both show as records.
- Numbers quoted as text read as numbers, so a time to live reads the same on both generations.
- The reasons the server gives for the session's risk, and any rule it says fired, are shown with
  the transaction, in the server's own words.
- The query name, the answer data and the transaction identifier can each be copied in one action,
  and what lands on the clipboard is the raw value, not its formatting.
- Nothing decoded is lost by specialising: everything the layout does not place is still on screen,
  as it is for every other protocol.
- The layout is built from the payload the session already carries, so it is on screen as soon as
  the session is; it asks the server for nothing the generic view did not.
- A DNS session with nothing decoded says so, exactly as the generic view does.

## Acceptance criteria

1. A DNS session shows the question and the answer as a transaction, not as a flat field list —
   current: NO → expected: YES.
2. A response code that arrives as a bare number is shown with its name — current: NO → expected:
   YES.
3. An older-decoder session whose authority is a single record shows that record among the answer —
   current: NO → expected: YES.
4. A time to live quoted as text reads the same as one quoted as a number — current: NO → expected:
   YES.
5. The flags read as the names of the ones that are set — current: NO → expected: YES.
6. The server's stated reason for the risk appears with the transaction — current: NO → expected:
   YES.
7. Copying the query name puts exactly that name on the clipboard — current: NO → expected: YES.
8. Everything decoded is still visible, including what this layout does not place — current: YES →
   expected: YES (must not regress).
9. A session of any other protocol is unchanged — current: YES → expected: YES (must not regress).
10. Opening a DNS session sends no request the generic view did not already send — current: unknown
    → expected: YES.

## Open questions

- Whether to mark a query name that looks machine-generated. The server flags the burst at the level
  of the session's risk, not the name; marking the name ourselves would be our judgement, not the
  server's. Proposed: show the server's reason, leave the name unmarked.
- Whether the copy action needs to work in the e2e browser, where clipboard access is granted per
  context. Proposed: prove the copied value in a component test and prove the control exists in the
  end-to-end flow.
