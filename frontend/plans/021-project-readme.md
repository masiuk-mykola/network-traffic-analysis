# 021 — The project README (implementation plan)

Read this before implementing. The spec is `specs/021-project-readme.md`.

## Decisions taken (the spec's open questions, answered)

- **The estimate defect is fixed first**, so the README describes a working app rather than a known
  fault. The fix is the first half of this step; the README is the second.
- **The AI section follows the shape used in the author's previous submission** (`../../mobile-
coding-challenge-Mykola-Masiuk/README.md`): _what I did_ / _what Claude Code did_ / _why this is
  worth saying_. The author's own list is written from what is on the record in this repository —
  decisions, corrections and rejections — and the author edits it before sending.

## Part one: the defect

`GET /v1/estimate` takes repeated `f=` parameters and **ANDs them** — its own description says so,
and there is no parameter for a join. The form, meanwhile, lets conditions be joined with **any**.
So _source is X or destination is X_ is estimated as _source is X and destination is X_: the line
reads "No sessions match this query" for a query the search then answers with hundreds. Found while
investigating, recorded in the README, now fixed.

The honest fix is to not ask a question whose answer cannot be right, and to say so where the number
would have been — not to invent a number, and not to silently show nothing.

| File                                          | Change                                                                                                                                          |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/search/estimate-params.ts`           | Return nothing to ask when the conditions are joined with _any_ and there is more than one of them.                                             |
| `src/lib/search/estimate-params.test.ts`      | One condition joined with _any_ is still askable; two are not; two joined with _all_ still are.                                                 |
| `src/app/(app)/search/estimate-line.tsx`      | When there is nothing to ask _because of the join_, say that the estimate cannot be given for this query and why, instead of rendering nothing. |
| `src/app/(app)/search/estimate-line.test.tsx` | The sentence appears for an any-joined query with two conditions, and no request goes out.                                                      |

## Part two: the README

| File                            | Change                                                                                                                                                                                                                                               |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/README.md`            | The full file, with the investigation kept as its own section. Sections: what this is; running it; the three screens; how it is arranged; what is done; what is not, and why; the tests; what was found broken in what was given; the AI disclosure. |
| `frontend/plans/000-roadmap.md` | Mark 5.2 done, at the end.                                                                                                                                                                                                                           |

## Steps

1. **Fix the estimate, test-first.** The rule belongs where the question is composed, not in the
   screen: a query the endpoint cannot express is not asked. The screen then explains the silence.
2. **Say it on screen.** The line distinguishes "nothing to ask yet" (an incomplete query) from
   "cannot be asked" (an any-joined query), because only the second needs explaining.
3. **Collect the facts for the README from the repository, not from memory.** The number of tests and
   e2e specs, the exact commands from the scripts, the pinned versions, and the current verdict from
   the backend's own report. Anything that cannot be produced by running something is not written.
4. **Write the running instructions in the order a reader types them**: the API first (Docker
   compose, or the backend's own runner), the environment file, then the app. Each command copied
   from what is actually in this repository.
5. **Describe the shape in a paragraph**: the token never reaches the browser, the browser talks only
   to this app's own handlers, reads go through one proxy that validates them against the API's
   published schemas, and the session store keys tokens by an opaque cookie.
6. **List what is not built and why** — the rest of the states work, the keyboard pass, the table
   performance work, and the whole optional phase — separating "not needed" from "not reached".
7. **Point at the tests**: the unit suite and what it covers, the end-to-end specs against a live API,
   and the backend's own grading of this client, which is the one that checks the things a frontend
   test cannot see.
8. **Report what was found broken in what was given**: the two faults that stopped the backend from
   starting as shipped, and the two places where the API's document and its behaviour disagree.
9. **Write the AI disclosure** in the agreed shape, from the record.
10. **Check every command in the file by running it.**

## Risks

- **A README that lies by being stale.** Counts and commands go out of date the moment they are
  guessed. Every number in the file is taken from a command run while writing it, and step 10 runs
  them again.
- **Claiming the human's work.** The _what I did_ list is assembled from decisions actually recorded
  in this repository's specs and history; the author edits it before sending. Nothing is attributed
  to anyone on the strength of a guess.
- **The estimate fix hiding a real zero.** A query that genuinely matches nothing must still say so.
  The change only removes the question when the endpoint cannot express the join — one condition, or
  an all-joined set, is unaffected.
- **Breaking the debounce.** The estimate is rate-limited by the server and the app already waits for
  a settled query; the new rule runs before the request is composed, so it removes requests rather
  than adding them, and `estimate.rate` stays clean.
- **Documenting defects unfairly.** The two backend faults are stated as what was observed and how it
  was worked around, with no claim about why they are there.

## Verification

| Spec criterion                      | Proof                                                                                                                  |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 1 — a reader gets a running system  | Follow the file's own commands from a clean shell; the app answers on its port against the API.                        |
| 2 — done and not-done, with reasons | Read the file against the roadmap: every unfinished item appears with its reason.                                      |
| 3 — the tests are pointed at        | Each command in the testing section is run; the counts in the file match what they print.                              |
| 4 — the defects found are named     | The four are in the file: two that stopped the backend, two contract mismatches.                                       |
| 5 — the AI disclosure               | Present, in the agreed shape, with the author's line left for the author.                                              |
| 6 — every command works as written  | Step 10: run them all.                                                                                                 |
| 7 — the investigation survives      | The section is still there, its links still open from a cold start.                                                    |
| The estimate fix                    | Unit tests on what is asked; a component test for what is said; `capture-api report` with `estimate.rate` still clean. |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
