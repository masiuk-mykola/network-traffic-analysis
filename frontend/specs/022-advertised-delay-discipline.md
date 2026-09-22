# 022 — Honour every advertised delay, whoever asks next

## Context

The server grades the client it talks to. One of its checks is that when it refuses a request and
names how long to wait, nothing asks about the same thing again inside that wait. Under its calm and
its token-expiry profiles the client passes every check; under its storm profile — where a fifth of
all reads are refused — that one check still fails, rarely and unpredictably, around the running
search.

Two causes were found and fixed earlier, both of the same shape: a delay was heard by one part of
the interface and not by another. A third case survives. It was written down as unresolved rather
than left for a reviewer to find, because it could not be reproduced on demand: the end-to-end suite
aborts on the first refusal that breaks an assertion, long before enough traffic accumulates.

Reading the server's own scoring rule changes the picture in one important way. The wait it opens
does not belong to a single request or a single search — it covers **the kind of address**, for the
whole signed-in session, and it is closed by **any** next request to that kind of address, including
one that deletes rather than reads. The earlier framing of the failure as "the status read asked
twice" was too narrow, which is part of why it resisted isolation.

This is the last known failing check in the project.

## Goals

- Reproduce the failure deliberately, rather than waiting for it, and attribute it to a named caller.
- Remove the cause at its source, so that no part of the interface can ask about something inside a
  delay that another part was given for it.
- Leave the project's own account of its behaviour accurate: what was found, what was fixed, what
  was ruled out.

## Non-goals

- The optional capabilities the roadmap parks in its final phase. None is started here.
- Any change to the server. It is given and correct.
- Widening the reproduction into a permanent part of the end-to-end suite. The suite is deliberately
  deterministic about failure; a traffic generator that runs for minutes belongs outside it.
- Making the interface slower or more cautious in the ordinary case. A delay that was never
  advertised must change nothing.

## Requirements

- When a refusal names a delay, every later request about the same kind of thing — a read, a repeat
  of the same read from a different part of the app, a cancellation, or the replacement of one job
  by another — waits out the remainder of that delay before it is sent. This holds whether the
  refusal was received while rendering on the server or in the browser, and whether the next request
  comes from the other side of that boundary or the same one.
- The memory of a delay survives the things that currently lose it: a screen rendered again, a
  navigation, a component mounted a second time, and a cached answer being discarded.
- While a request is being withheld for a delay, the reader is told what the screen is waiting for
  rather than shown a silent stall, and the wait is visibly finite. The existing vocabulary for
  loading, empty and failed states is used; nothing new is invented for this.
- A user action that cannot be sent immediately — cancelling a running search, or starting one that
  replaces another — is not silently dropped. It either happens once the delay has passed, or it
  says why it cannot happen yet.
- A refusal that names no delay behaves exactly as it does today.
- The delays involved are short — a few seconds — so nothing may hold a user action for longer than
  the server actually asked for.

## Acceptance criteria

- **AC-1.** A refusal that names a delay, received while the screen is being prepared, is not
  followed by a request about the same thing from the browser inside that delay.
  _current: NO → expected: YES_
- **AC-2.** A refusal that names a delay, received in the browser, is not followed by a request
  about the same thing while the screen is prepared again after a navigation.
  _current: NO → expected: YES_
- **AC-3.** Cancelling a running search, or starting a search that replaces one already running,
  does not reach the server inside a delay the server named for that kind of address.
  _current: NO → expected: YES_
- **AC-4.** The list of matched sessions is not asked for again inside a delay that its own refusal
  named. _current: NO → expected: YES_
- **AC-5.** With every read refused and a delay named on each, a session driven through signing in,
  searching, following, re-navigating and cancelling produces no violation of an advertised delay in
  the server's report. _current: NO → expected: YES_
- **AC-6.** Three consecutive runs of the same session under the server's storm profile produce no
  violation of an advertised delay in its report. _current: NO → expected: YES_
- **AC-7.** The other two profiles and the toolchain check continue to report no failure.
  _current: YES → expected: YES_ (regression guard)
- **AC-8.** A refusal that names no delay is followed by the same retry behaviour as before, at the
  same moment. _current: YES → expected: YES_ (regression guard)
- **AC-9.** The project's written account of its behaviour under the storm profile matches what the
  report now says, including the third cause. _current: NO → expected: YES_

## Open questions

Answered by the author on 2026-09-22, before the plan was written. Kept with the answers rather than
deleted, because the plan's decisions only make sense next to the question they settle.

1. **Where the shared memory of a delay belongs.** — **Answered: on the server, in front of the
   proxy.** Every request the browser makes and every read a screen makes while rendering pass
   through the same handlers, so one memory there covers both sides and every method, which is what
   the server's rule actually scores. It is per-process and does not survive a restart; accepted,
   because the behaviour being graded is one reader's within one session.
2. **What a withheld user action should look like.** — **Answered: wait, then act.** The control
   says what it is waiting for and the request goes out by itself once the delay has passed. The
   delays are one to three seconds; making someone click twice for that is worse than making them
   wait once. The countdown on a refused sign-in stays as it is — there the wait can be minutes.
3. **Whether the third cause is one of the three candidates already identified, or a fourth.** —
   **Answered on 2026-09-22 by the reproduction: a fourth, and it is not the search status read at
   all.** The offender is `/v1/me` — the profile the guard resolves on every navigation.

   `e2e/retry-after-gate.ts` under forced refusals produced it on the first run, and the server
   agreed. The matched pair, from the log at the seam:

   ```
   195.607  GET /v1/me  refused 503 retry-after=1000
   195.711  GET /v1/me  send                              <- 104 ms later, inside the window
   ```

   ```
   FAIL http.retry_after_violations
     GET /v1/me -> 503 — retried 0.17s after a 503 asking for 1s
   ```

   The caller is `requireProfile` (`src/lib/auth/session.ts`), reached from the `(app)` group's
   layout. `shareProfileRead` shares the read _in flight_ and keeps nothing once it settles, so a
   refusal is forgotten the instant it is thrown; the next navigation — or the error boundary
   re-rendering the same one — asks again inside the delay. Nothing in the search code is involved,
   which is why every attempt to isolate it around the search status read failed.

   The same run also caught the search status read, for a different reason:

   ```
   193.877  GET /v1/searches/srch_52d…  refused 503 retry-after=2000
   195.710  GET /v1/searches/srch_52d…  send                          <- 1.83 s later
   ```

   Here `pollDelay` did wait — but it measures the delay from when the _browser_ received the
   refusal, while the server measures from when _it_ received the request. The round trip through
   our own proxy is the difference, and it is enough to undershoot a 2 s window. A browser-side
   wait cannot close this on its own; a wait taken on the server, after it has seen the response,
   can. That is a second argument for the seam, independent of which caller offends.

4. **How long the traffic generator should be kept.** — **Answered: kept, as a script beside the
   end-to-end suite**, not as part of it, so the gate can be re-run by the next person. Mentioned in
   the project README with the command.

Next step: /plan specs/022-advertised-delay-discipline.md
