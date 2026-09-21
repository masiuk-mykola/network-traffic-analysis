# 020 — Report the compromise (implementation plan)

Read this before implementing. The spec is `specs/020-report-the-compromise.md`.

## Decisions taken (the spec's open questions, answered)

- The write-up goes **in the project's README**, short enough to read in place.
- The evidence is **a session link and a query link**: the session stands alone, the query lets the
  reader see the pattern at its full size by running it themselves.

## What this step is, and is not

This is an investigation with a written result, not a feature. Almost nothing here is code: the only
file that must change is the README. The discipline that matters is where the answer may come from —
the interface, driven as a reader drives it — and what the write-up is allowed to claim.

**The rule for this step:** the backend's source, its fixtures, its seed data and its observer output
are off limits as a source of the answer. They may be used for nothing at all here. If a fact cannot
be reached through a screen, it does not go in the write-up.

## What the interface already gives the investigation

| Tool                             | Where it helps                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------- |
| Conditions over published fields | Narrow by protocol, address, port, country, risk — the fields the server itself names.         |
| Results ordered by risk          | The server's own scoring, so the search starts where the server is already suspicious.         |
| A session in full                | The decoded transaction, and the reasons the server gives for its risk.                        |
| Traffic over time                | Whether a session is a burst or a trickle — the shape that separates a beacon from a download. |
| Related sessions, three windows  | The neighbours of a session: the same pair of machines, minutes either side.                   |
| A shareable query in the address | Capture points, window and conditions travel in the address; a started job does not.           |

## Files to touch

| File                            | Change                                                                                                                                                                                            |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/README.md`            | Replace the framework's boilerplate with the finding: the machine, when it starts, the links, the path taken, and what was ruled out. Only the finding — the rest of the README is the next step. |
| `frontend/plans/000-roadmap.md` | Mark 5.1 done at the end.                                                                                                                                                                         |

No source file is expected to change. If the investigation runs into something the interface cannot
do, that is written into the README as a gap and raised — not fixed inside this step.

## Steps

1. **Start where the server is already suspicious.** Search the whole capture window across all three
   capture points, ordered by risk, and read what the server itself flags — the risk reasons it
   attaches and any rules it says fired. Note the shapes that recur.
2. **Separate the noise.** The task warns that the capture contains things that look suspicious and
   are not. Take the loudest recurring pattern and test it: who does it, how often, at what hours, to
   where. A pattern spread across many machines, or explained by an ordinary service, is noise —
   record which one was dismissed and why, because the write-up has to name at least one.
3. **Follow one machine, not one session.** For each candidate, pivot: open a session, read its
   decoded transaction, look at its traffic over time, and walk its neighbours in the three windows
   the server offers. The question is which machine has a _story_ — a first odd thing, then more.
4. **Find where it starts.** Narrow the window towards the earliest session that belongs to the
   pattern, by moving the window rather than by guessing: the address bar carries the window, so each
   narrowing is reproducible.
5. **Prove it twice.** One session link that shows the thing itself, and one query link that a reader
   can run to see the whole pattern. Check both from a cold start: a fresh sign-in, no job of ours
   alive, following the link and nothing else.
6. **Write it up** in the README: the machine as the capture names it, the first moment, the two
   links, three or four sentences on the path, and the dismissed suspect with its reason. Mark
   plainly which statements are the server's and which are ours.
7. **Re-read it against the criteria** and remove anything that cannot be re-checked by following a
   link.

## Risks

- **Answering from the backend by accident.** The seed, the fixtures and the observer's own output
  would all give the answer away. They are not opened during this step; the only permitted sources
  are the screens and the API's published contract.
- **A link that dies.** A search job is per-account and the server discards it when unread, so a link
  carrying a job id is worthless tomorrow. Only the session link and the re-runnable query link go in
  the write-up, and both are checked from a fresh sign-in.
- **Mistaking the loudest pattern for the answer.** The capture is built to bait exactly that; the
  write-up must name what was dismissed, which is only possible if step 2 actually tests it rather
  than assuming.
- **Reading a uint64 as a number.** Session ids are copied as strings, from the address bar, never
  retyped or rounded.
- **Exhausting the search slots.** The investigation will run many searches; each one holds one of
  three slots until it is deleted, and an abandoned job is scored. Supersede rather than accumulate,
  and let the app delete what it replaces.
- **Rate limits while exploring.** The estimate endpoint is rate-limited and health polling is graded;
  a long exploratory session must not turn into a stream of refusals. The app already debounces and
  waits out the delays it is given — if the report shows otherwise afterwards, that is a finding.
- **Asserting a motive.** The capture shows traffic, not intent. The write-up says what the traffic
  shows and marks anything beyond that as inference.

## Verification

| Spec criterion                                    | Proof                                                                                                           |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 1 — the machine and when it starts are named      | Read the README: both present, with the identifier the capture uses.                                            |
| 2 — the links open the evidence from a cold start | Sign in fresh in a clean browser session, follow each link, confirm the evidence is on screen.                  |
| 3 — the path is explained                         | The README's few sentences name the screens used, in order.                                                     |
| 4 — a dismissed suspect is named with a reason    | Present in the README, and the reason is checkable through the same interface.                                  |
| 5 — every claim is supported by the interface     | Walk the write-up line by line against the screens; anything unsupported is cut.                                |
| 6 — nothing depends on temporary state            | The links carry no job id; the cold-start check in criterion 2 is the proof.                                    |
| 7 — the investigation used the interface only     | The commit for this step touches the README (and the roadmap) and nothing else; no backend file is read for it. |

The standing gates still run — `npm run format:check`, `npm run lint`, `npm run typecheck`,
`npm run test`, `npm run build` — but they only prove nothing was broken. After the exploration,
`capture-api report` is checked once more: a long investigative session is exactly the kind of use
that would expose duplicate reads, abandoned searches or ignored delays.
