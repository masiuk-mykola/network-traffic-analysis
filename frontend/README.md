# Capture — a web interface for traffic forensics

A Next.js interface for the capture API in `../backend`: sign in, search three days of captured
traffic from three capture points, and read one session in full. The browser never talks to the API
directly — it talks to this app, and this app holds the token.

## Running it

**1. The API** (Python 3.13 and [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run capture-api serve          # http://localhost:8700
```

Or, without installing uv, from the repository root: `docker compose up -d --build`.

**2. This app** (Node 20+):

```bash
cd frontend
cp .env.example .env.local        # CAPTURE_API_URL, read on the server only
npm ci
npm run dev                       # http://localhost:3000
```

`npm run predev` regenerates the API types and the zod schemas from the running API before every
`npm run dev`, falling back to the committed `backend/openapi.json` when the API is down.

**Both in Docker**, with the app reloading from the source tree:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Sign in with the demo accounts the sign-in screen lists: `ana@quillmere.example` / `demo-analyst`
(an analyst) or `oli@quillmere.example` / `demo-observer` (an observer, who sees sensitive values
withheld).

## The three screens

- **Sign in** — email and password. The token stays on the server; the browser gets an opaque
  session cookie.
- **Search** — pick up to five capture points and a window, build conditions from the fields the
  server publishes, see an estimate of the size before running, start the job, follow its progress,
  and read the results as they arrive. The query, the job and the sort order live in the address, so
  a search can be handed to someone else.
- **Session** — one session in full: a summary, the decoded transaction built from the server's own
  description of that protocol, a first-class layout for DNS, a timeline of its traffic, and the
  sessions the server relates to it.

## How it is arranged

The API has CORS off and takes a bearer token, so nothing in the browser may reach it. Signing in
happens in a route handler that keeps both tokens in a server-side store keyed by an opaque cookie
and hands the browser only a profile. Every read goes through one proxy handler that attaches the
token, refreshes it once on a 401 — single-flight, because a reused refresh token kills the session
— and validates the answer against zod schemas generated from the API's own document before it
reaches a screen. Writes, which are starting and deleting a search, have their own handlers.

On the client, TanStack Query owns every read, every cache key is built in one place, and there is a
single reaction to a session that has died: cancel everything, clear the cache, explain, and leave.

Two reads are rationed rather than proxied: the field catalogue and the server's own condition. Both change on the scale of a deploy, and the
API counts identical reads and treats one that follows a refusal too soon as a violated delay — so
one answer is held behind a single-flight read, however many tabs, navigations and renders ask for
it. The trade is deliberate: a part of the server going unwell, or recovering, shows up to half a
minute late.

Path aliases: `@api/*` → `src/lib/api/*`, `@lib/*` → `src/lib/*`, `@/*` → `src/*`.

## What is done

Signing in, with a guard on every protected screen. The search form: capture points, a window
derived from the last traffic each point reported — this capture ends in the past, so a window built
from the clock would return nothing — conditions built from the published fields, and a debounced
estimate of the size. Starting a search with an idempotency label derived from the query itself,
following it with a backoff that pauses in a hidden tab, cancelling it, and freeing its slot. A
virtualised results table built from the columns the server publishes, paged by cursor, sortable
once the job has finished. The session screen described above. And failure handling that keeps a
refused read from taking the whole screen with it. Values the server withholds from an observer read
as withheld rather than as the marker it sends, the list behind a closed-field condition can be
retried or bypassed by typing, and a part of the server the server itself reports as unwell is quoted
once above every screen.

## What is not done, and why

- **A keyboard and focus pass** (4.3): the screens are keyboard-reachable and Radix manages focus in
  the dialogs, but there was no deliberate audit, so I will not claim one.
- **Table performance work** (4.4): the table is virtualised and holds up at the sizes this capture
  produces. Nothing was measured to be slow, so nothing was optimised — skipped on purpose rather
  than unfinished.
- **The optional protocols** (phase 6): the live detection feed over SSE, WebSocket, PCAP and carved
  file downloads, saved queries, IP enrichment. Each switches on more of the backend's scored checks
  and none is needed for the three screens the task asks for.
- **Deployment**: nothing is deployed anywhere; the task did not ask for it.

## The tests

```bash
npm run test                      # 416 unit tests in 58 files
npm run test:e2e                  # 67 end-to-end tests in 15 files, against a live API
npm run format:check && npm run lint && npm run typecheck && npm run build
```

The unit tests cover the places where being wrong is silent: cursor and window handling, the
condition grammar and its form in the address, the retry policy, the redaction marker, both decoder
generations of DNS, the timeline's bucket widths, and every cache key. The end-to-end specs drive
the real screens against the real API — signing in, running a search, reading results, opening
sessions — including the failure paths, which are forced by refusing one specific read rather than
by waiting for the server's own chaos to misbehave.

There is a third kind, and here it is the one that matters most:

```bash
cd backend && uv run capture-api report
```

The API grades the client that talked to it: refresh discipline, duplicate reads, cursors used
verbatim, `Retry-After` honoured, searches cancelled rather than abandoned, health polling kept
calm. No frontend test suite can see any of that. After a full end-to-end run it reports **0 fail**.

## What was broken in what was given

The task invites this, so: four things, two of which stopped the backend from starting as shipped.

- **`backend/README.md` was missing from the archive**, and both `pyproject.toml` and
  `backend/Dockerfile` expect it. `uv sync` and the image build failed until it was put back.
- **The image's `CMD` names `capture_api`**, while the console script installed by `pyproject.toml`
  is `capture-api`. The container exec-failed on boot; `docker-compose.yml` overrides the command
  rather than editing the backend.
- **`/v1/meta/columns` publishes a column type the API document does not list** (`geo_hint`).
  Validating responses against the generated schemas — which is the point of generating them —
  rejected a perfectly good answer. That one read is now validated with a shape that keeps the
  vocabulary open, with the reason written next to it.
- **`Idempotency-Key` is honoured but not declared.** The create-search endpoint describes it in
  prose and acts on it, but it is not in the parameter list, so no generated client knows it exists.

One more, in the API's shape rather than in its behaviour: **`/v1/estimate` ANDs its filters and has
no join**, while a search accepts any-of. This app used to estimate an any-joined query as a
conjunction and report a confident "no sessions match this query" for a query the search then
answered with hundreds. Found during the investigation below, and fixed: the estimate is not asked
when it cannot be expressed, and the screen says why.

## The compromised machine

**`ws-hb-009.quillmere.example` (10.20.40.18), seen at the `harbor-branch` capture point.**

It starts at **2025-10-25 03:11:38.456 UTC**, fifteen minutes before anything else happens: the
machine resolves `telemetry.static-assets-cdn.test`, a name that appears nowhere else in the capture
before that moment.

- [The first lookup](http://localhost:3000/sessions/216172823837671425) — `A
telemetry.static-assets-cdn.test → 203.0.113.201`, answered with a sixty-second time to live. The
  server scores it 46 and gives one reason: _rarely seen domain_.
- Ten and twenty-five seconds later, two more lookups under the same parent with random-looking
  labels — `71dbe240.static-assets-cdn.test`, `96a10af4.static-assets-cdn.test` — both answered
  _no such name_.
- [The first call home](http://localhost:3000/sessions/216172823853400065), at **03:26:56.200 UTC**:
  TLS 1.2 to `203.0.113.201:443` (Austria), 4.3 kB, 1.5 s. The server's reasons: _self-signed
  certificate_, _certificate name does not match SNI_, _rarely seen domain_.
- [Every call home, oldest first](http://localhost:3000/search?sensor=hq-core&sensor=dc-east&sensor=harbor-branch&from=2025-10-24T00%3A00%3A00.000Z&to=2025-10-28T00%3A00%3A00.000Z&f=tls.sni%3Aeq%3Atelemetry.static-assets-cdn.test&sort=ts)
  — press **Run search**. 668 sessions across the three days of the capture, all from this one
  machine, one every five to six minutes, each around four kilobytes, from 03:26 on 25 October until
  the capture ends.

What the server asserts is quoted above. **Our conclusion** is the shape: one host, one destination,
a fixed small payload at a fixed short interval, through a certificate that does not match the name
it claims — traffic that keeps a channel open rather than doing anything a person asked for. The
capture shows traffic, not intent; nothing here says what was taken.

### How it was found

1. Searched the whole capture across all three points and ordered by the server's own risk. The top
   of that list is a SYN sweep — loud, but see below.
2. Excluded that one host from the same query. What surfaced was `10.20.40.18` calling
   `telemetry.static-assets-cdn.test` over and over, scoring 70–84 every time.
3. Opened one of those sessions and walked _around this session_ — the neighbours the server relates
   to it — which showed the same pair of machines every few minutes, all day.
4. Narrowed the window backwards until the pattern stopped: nothing before 2025-10-25 03:26, and one
   quiet DNS lookup of the same name fifteen minutes earlier. That lookup is where it starts.

### What was ruled out

- **The port scanner, `scan-it-01.quillmere.example` (10.20.9.250).** It owns the highest scores in
  the capture — the server calls it _port-scan pattern · T1046_, 86 out of 100 — and it sweeps
  hundreds of hosts across dozens of ports. It is also entirely internal: every connection is
  128–148 bytes with no payload, from a machine whose name says what it is, and nothing it touches
  ever leaves the network. Loud, scheduled, and not the answer.
- **The random-looking DNS names.** Lookups like `c81e40ba.packages.example.net` answered _no such
  name_ look exactly like a domain-generation algorithm, and the server flags the bursts
  (_burst of NXDOMAIN answers · T1568.002_). Searching for them across the capture returns roughly
  twenty different machines at all three capture points, against many unrelated parent domains, most
  scoring in single digits. A pattern that names twenty machines names none of them — background
  noise. (The compromised host makes two such lookups of its own, which is why the pattern is worth
  checking rather than dismissing on sight.)

### A gap this investigation found in the interface

When conditions are joined with **any**, the estimate shown next to the run control is wrong: the
estimate endpoint only accepts conditions that are ANDed together, so a query like _source is X or
destination is X_ is estimated as _source is X **and** destination is X_ — which is impossible, and
the line reads "No sessions match this query" for a query that in fact matches hundreds. The search
itself is correct; only the estimate is. It is not worked around: it is written down here, and the
honest fix is to say the estimate cannot be given for an any-joined query rather than to show a
number that is not true.

## AI disclosure

This was built with **Claude Code** (Anthropic) as a pair-programmer. No other AI tool was used. How
it was used is part of the work: the agentic setup is committed to this repository in
[`.claude/`](.claude) so it can be inspected, and every step of the work is in `specs/` and `plans/`.

It was built with two practices, deliberately, and they are visible in the repository rather than
merely claimed:

- **Spec-driven development.** Nothing was written before it was specified. Each step began with a
  spec that answers _what_ and _why_ in half a page — goals, non-goals, requirements, and acceptance
  criteria written as `current: NO → expected: YES` — and anything unconfirmed went into **Open
  questions** rather than into requirements. Only then came a plan that answers _how_: real file
  paths, ordered steps, the races and edge cases that could bite, and a table mapping every
  acceptance criterion to the thing that proves it. The 21 specs in [`specs/`](specs) and the 22
  plans in [`plans/`](plans) are those documents, numbered in pairs, in the order the work happened.
- **AI agentic engineering.** The agent works inside a harness I set up rather than from a chat
  prompt: rules that are always in force ([`.claude/rules`](.claude/rules)), slash commands for the
  pipeline ([`.claude/commands`](.claude/commands) — `/spec`, `/plan`, `/implement`, `/code-review`),
  sub-agents for the jobs a single pass does badly ([`.claude/agents`](.claude/agents) — an
  architect, a planner, a code reviewer, a plan verifier), skills that encode this project's own
  conventions and the HTTP discipline the backend scores ([`.claude/skills`](.claude/skills)), and
  hooks that enforce the boundaries mechanically ([`.claude/hooks`](.claude/hooks)): git writes
  denied, dangerous shell commands denied, files holding secrets unreadable, and the formatter and
  the related tests run after every edit.

Open questions were answered by me, one at a time, before a plan could be written — which is why the
specs carry proposals and the plans carry decisions. Where the answer changed the design, the plan
says so.

**What I did**

- **Set the engineering process** described above, and carried it over from my previous project:
  research before code, behaviour as test statements, unknowns surfaced instead of guessed, and a
  hard boundary that keeps the agent out of git — every commit in this history is mine.
- **Made the product decisions.** Timestamps in UTC everywhere; the default window derived from the
  last traffic rather than from the clock; the query, the job and the sort order in the address; the
  idempotency label derived from the query; polling from half a second to five, paused in a hidden
  tab; sorting offered only once a search has finished; the flow timeline on one shared scale with
  the two directions mirrored; the related list's window kept local to the screen; withheld values
  marked field by field; and anomalies reported only in the server's own words.
- **Set the scope, and cut it.** I stopped the polish phase when it stopped paying — the health
  banner and the performance pass were dropped on purpose — and moved the remaining time to the
  investigation and this file, which is what the task actually asks for.
- **Reviewed and corrected.** I sent the first pass at the design back as unusable (a run control
  that looked like an input, no hover states anywhere), rejected comments written in the wrong
  language and in the wrong quantity, caught the CI failure, and read the diffs.

**What Claude Code did:** wrote the specs and plans from those decisions, implemented the code and
the tests test-first, drove the real screens to find the compromised machine, and reported its own
failures honestly — including the estimate defect above, which it found while investigating rather
than while testing.

**Why this is worth saying:** the interesting part was not generating code. It was the process around
it — gates the work has to pass, unknowns it has to surface instead of inventing, and a human
decision behind every trade-off.
