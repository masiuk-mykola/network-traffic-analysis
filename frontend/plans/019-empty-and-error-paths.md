# 019 — Finish the empty and error paths (implementation plan)

Read this before implementing. The spec is `specs/019-empty-and-error-paths.md`.

## Decisions taken (the spec's open questions, answered)

- The degraded notice is **one line at the top of the application**, under the header, visible on
  every screen, gone when the server is well again. It is about the server, not about a screen.
- A withheld value is marked **field by field**, where the reader is looking. The role is already in
  the header, so no per-session summary is added.

## What the server actually does (probed 2026-09-21)

| Fact                                                                                                                                                      | Consequence                                                                                     |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| The two roles differ in data, not in permissions: an observer creates searches (202) and reads everything.                                                | No "no access" screen is built. The work is in rendering withheld values.                       |
| An observer's payload carries `{"redacted": true}` in place of a value — HTTP `authorization`/`cookie`/`set-cookie` headers, SMTP `rcpt_to`, SMB2 `user`. | A marker, not a string: the renderer must recognise the shape, not a magic string.              |
| Our formatter falls through to `JSON.stringify`                                                                                                           | Today that marker is printed as `{"redacted":true}` — the bug this step fixes.                  |
| `/v1/health` answers `status` plus a component map, each with a `detail` sentence                                                                         | The notice quotes the server; nothing is composed by us.                                        |
| Under `storm`: `index: degraded — "The session index is rebuilding; searches may be slow or fail."`                                                       | There is real copy to show, and a real way to test it (set the profile, read, restore).         |
| `poll.health_interval` grades the median gap between health reads at **≥ 10 s**                                                                           | The new read is slow by construction and pauses in a hidden tab, like the search poll.          |
| Nothing in the app reads health today (the 10 s median in the report comes from the compose healthcheck)                                                  | Our reads join that stream — so a too-eager interval would break a check that currently passes. |

## Files to touch

| File                                                                     | Change                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/format/redacted.ts` (new)                                       | `isRedacted(value)` — recognises the server's marker object (and only that), plus the wording shown in its place.                                                                                                         |
| `src/lib/format/redacted.test.ts` (new)                                  | The marker; a value that merely has the word in it; `false`; a nested marker inside a list; an ordinary object.                                                                                                           |
| `src/lib/format/value.ts`, `index.ts`                                    | The shared formatter returns the withheld wording for a marker instead of falling through to JSON.                                                                                                                        |
| `src/lib/format/value.test.ts`                                           | A marker under several column types, so no screen can print it raw.                                                                                                                                                       |
| `src/app/(app)/sessions/[id]/transaction.tsx`                            | A withheld row is marked as such (the mark reads "withheld for your role"), and the value cell shows the wording, not data.                                                                                               |
| `src/lib/session/dns.ts`, `src/app/(app)/sessions/[id]/dns-exchange.tsx` | A record value that is withheld renders as withheld in the first-class view too (DNS carries no sensitive field today, but the layout must not print a marker if one appears).                                            |
| `src/app/(app)/sessions/[id]/session-view.test.tsx`                      | An observer-shaped payload: the wording is on screen, the marker is not, and an analyst-shaped one still shows its values.                                                                                                |
| `src/lib/search/use-enum.ts`                                             | Nothing structural; only what the control needs to tell its states apart (already exposes them).                                                                                                                          |
| `src/app/(app)/search/value-input.tsx`                                   | The closed-field control gains its failed state: a retry beside it, and — when the list cannot be read — a plain text entry so the condition can still be written.                                                        |
| `src/app/(app)/search/value-input.test.tsx` (new)                        | Loading; failure with a retry that re-reads; a failed list still lets a value be typed; a field with its values inline needs no read at all.                                                                              |
| `src/lib/health/use-health.ts` (new)                                     | The health read: slow interval, paused in the background, one entry in the cache, and a `degraded` summary derived from the component map.                                                                                |
| `src/lib/health/use-health.test.tsx` (new)                               | The interval is no faster than the server's limit; nothing is asked while hidden; a degraded component is summarised with the server's own detail; an unreachable health read is silent (it is not the reader's problem). |
| `src/components/server-notice.tsx` (new)                                 | The one-line notice: the server's sentences, dismissible for the session, reappearing if a new component degrades.                                                                                                        |
| `src/components/server-notice.test.tsx` (new)                            | Shown while degraded, gone when well, quotes the server, and says nothing when health cannot be read.                                                                                                                     |
| `src/app/(app)/layout.tsx`                                               | Render the notice under the header, above the screens.                                                                                                                                                                    |
| `e2e/states.spec.ts`                                                     | Two additions: with the server degraded, the notice quotes it and then disappears once calm; the observer sees withheld values on a session and no raw marker.                                                            |
| `CLAUDE.md`, `plans/000-roadmap.md`                                      | Two convention lines; mark 4.2 done. At the end, not during.                                                                                                                                                              |

Deliberately not touched: the redaction itself, the retry policy, the estimate line (its failure is
already reported and a retry there would re-ask a rate-limited endpoint), and every state that works.

## Steps

1. **Recognise the marker, test-first.** `redacted.ts` is three lines and one decision: the marker is
   an object whose only meaningful key says so. A string containing the word is not a marker, and
   `{redacted: false}` is not one either.
2. **Teach the shared formatter.** Every screen already formats through it, so one change covers the
   generic transaction, the results table and anything later. Test it under several column types.
3. **Mark the row, not just the value.** In the transaction the withheld field carries the same kind
   of mark the schema's sensitive flag already uses, with wording that names the role as the reason.
4. **Cover the first-class view.** DNS has no sensitive field today, so this is a guard rather than a
   fix: the record renderer must go through the shared formatter rather than printing a value.
5. **Give the closed-field control its missing state.** A failed list gets a retry, and falls back to
   typing — the condition is what matters, not the convenience of choosing. This is the one surface
   the audit found with no failure path at all.
6. **The health read.** A single query with a slow interval, paused in the background, no retry storm,
   and silence when it cannot be read: the reader has no use for "we could not ask how the server
   is". Derive one summary (degraded components with their sentences) rather than exposing the map.
7. **The notice.** One line under the header, the server's own words, dismissible for the session but
   re-armed when a different component degrades. Rendered from the layout so every screen inherits it.
8. **E2E**, then verify, then the documentation lines.

## Risks

- **Breaking a check that currently passes.** `poll.health_interval` grades the median gap of health
  reads, and the compose healthcheck already contributes. Our interval must be comfortably above the
  limit and must not run in a hidden tab; the verification reads that check explicitly.
- **A notice that cries wolf.** The server reports `degraded` for a component this app may not even
  use (the live feed, the packet store). The notice names what the server named and says what the
  server said — no interpretation, and no blocking of anything.
- **A marker that is real data.** Some payload might legitimately contain the word; matching the
  shape rather than a string is what keeps an ordinary value from being hidden.
- **Hiding too much.** The mark must not swallow the field's label or its path: a reader needs to know
  _what_ was withheld. Only the value is replaced.
- **A retry on the enum that the server rate-limits.** The enum catalogue is not rate-limited (the
  estimate is), and it is cached for half an hour, so a retry is cheap — but the fallback to typing is
  what makes the control usable if it keeps failing.
- **Chaos.** Under `storm` the health read itself can be refused; that path must stay silent rather
  than adding a second failure to a screen that already has one. Under `expiring-tokens` it refreshes
  like any other read.
- **The notice on the sign-in screen.** It belongs to the signed-in application only: the health read
  needs a session, and a refusal there must not appear as a failure before anyone has signed in.

## Verification

| Spec criterion                                        | Proof                                                                                                                      |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 1 — withheld reads as withheld, with the reason       | Unit tests on the marker and the formatter; component test with an observer-shaped payload; e2e signed in as the observer. |
| 2 — the analyst still sees the values (no regression) | The existing session-view tests, plus the same e2e flow as the analyst.                                                    |
| 3 — the role is visible on a session screen           | E2E asserts the role in the header while a session is open.                                                                |
| 4 — a failed value list reports and offers a way on   | Component tests on the control: retry re-reads; a value can still be typed.                                                |
| 5 — the degraded notice appears and then goes         | E2E: set the profile, read the server's sentence, restore, watch it disappear.                                             |
| 6 — health is asked rarely and not while hidden       | Unit test on the hook's interval and its background behaviour.                                                             |
| 7 — no unexplained blanks                             | The component tests above, plus the states already covered for every other surface.                                        |
| 8 — the verdict stays clean, including health polling | `capture-api report` after the suite: no FAIL, and `poll.health_interval` still passing.                                   |

Plus the standing gates: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`,
`npm run build`, `npm run test:e2e`.
