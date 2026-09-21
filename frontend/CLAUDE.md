@AGENTS.md

# Capture — frontend

Web interface for the traffic-forensics API in `../backend`. The backend is given and works:
never edit it.

## Commands

Run everything from `frontend/`.

```bash
npm run dev                 # http://localhost:3000
npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build
npm run test:e2e            # Playwright, starts its own dev server
npm run api:gen             # regenerate the types and the zod schemas from ../backend/openapi.json
```

The API must be up for anything past the skeleton. From the repository root:

```bash
docker compose up -d --wait simulator                              # API only, on :8700
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build   # API + this app with hot reload
```

`npm run predev` runs before `npm run dev` and regenerates the types and zod schemas from the running
API, falling back to the document committed in `../backend`. Run it by hand with `npm run api:sync`.

## Architecture

The API has CORS off and takes a bearer token, so the browser never talks to it directly.

- `src/lib/api/client.ts` — raw fetch with timeouts, `ApiError`, `Retry-After` parsing and optional
  response validation. No retries, no refresh.
- `src/lib/api/generated/zod.gen.ts` — zod schemas generated from the API document. Pass one as
  `schema` to a call and the body is validated before it reaches the UI; a mismatch raises
  `SchemaMismatchError` and never reaches the browser. Generated, never edited by hand.
- `src/lib/api/session-store.ts` — access and refresh tokens, keyed by an opaque session id.
  Refresh is single-flight per token family.
- `src/lib/api/server.ts` — `callApi()`: authorized call, one refresh and one replay on a 401.
- `src/app/api/**` — route handlers. `/api/auth/login` hands back only the profile,
  `/api/capture/[...path]` proxies GETs and validates the ones `@api/response-schemas` knows.
  Everything token-shaped stays behind `server-only`.
- `src/lib/api/keys.ts` — every cache identity, in one place; nested keys share their parent's
  prefix. `src/lib/api/fetch-json.ts` is the browser's only reader and throws `HttpError`,
  which carries the API's stable code and any advertised wait.

## Rules the backend scores

`uv run capture-api report` grades the client and must show no FAIL. Before changing the data layer,
read the `http-discipline` skill; the short version:

- one refresh in flight per family — a reused refresh token kills the session;
- no authorized request later than 5 s after logout; cancel queries, close streams, clear the cache;
- `Authorization` never leaves the server;
- at most two identical GETs per 100 ms — one `queryKey`, no raw `fetch` past React Query;
- honour `Retry-After` (an HTTP-date on login), never retry a 4xx blindly;
- cursors verbatim, `limit` <= 500, `/v1/health` no more than once per 10 s;
- three search slots: send `Idempotency-Key` on create, `DELETE` what you supersede.

## Conventions

- Comments and strings in code are English, and comments are rare — only where the code alone does
  not explain itself.
- Prettier owns formatting: single quotes, no semicolons, width 100. Run `npm run format`.
- Radix primitives (`@radix-ui/react-*`), not shadcn/ui. `cn()` from `@lib/utils` for classes.
- Protected screens live under `src/app/(app)/`; the guard is that group's layout, which resolves
  the profile once per navigation. Pages below it never check again, and only a missing session or
  a 401 redirects — an unreachable API reaches the error boundary instead.
- A session that dies mid-use is handled once, centrally: every browser read reports through
  `@lib/auth/session-expiry`, which cancels, clears, explains and leaves. No screen checks for it.
- A running search is polled with a backoff (half a second doubling to five), the interval comes
  from the job's state so it cannot outlive it, and a hidden tab asks nothing. A 410 means the
  server discarded an unwatched job — an ending to explain, not an error.
- Starting a search is a write, so it has its own handlers under `src/app/api/searches`; reads
  still go through the proxy. The idempotency label is derived from the query, so a retry replays
  the job already started, an unchanged query does not start a second one, and a changed query
  frees the old slot before taking a new one.
- The estimate is asked for a settled query only, never on a keystroke and never on a timer: the
  endpoint allows a few requests per second and the backend scores the refusals. While it loads,
  the previous number is removed rather than dimmed.
- Conditions are a flat list joined by all-or-any, each one negatable, built only from the fields
  the server publishes and the comparisons each field declares. They travel in the API's own
  `f=field:op:v1,v2` form, which `/v1/estimate` also accepts.
- The search query lives in the address bar: `@lib/search/query-params` parses it defensively (a
  shared link can name points this account cannot read) and the form mirrors changes back with
  `router.replace`.
- Forms are React Hook Form + zod through `@hookform/resolvers`; the schema is the source of the
  form's type. Responses are validated with the generated schemas, not hand-written ones.
- Results are a virtualized window over pages of 500: the table is built from the columns the server
  publishes (order, default visibility, widths, what may be sorted), never from a hard-coded set, and
  a column type or key it has never seen renders as text rather than breaking. While the job runs the
  order is fixed, and a page with no cursor means caught up, not finished.
- The order lives in the address with the query and the job, and is part of the results' cache
  identity — a cursor belongs to one order and the server rejects it in another. It is sent only to
  a finished job, because sorting a running one is refused. Starting a search or changing the order
  goes through the router so the entry can be returned to; every other edit rewrites the current
  address without a server render. A job the server does not have (404) is an ending to explain, not
  an error, and the page reads it once on the server so the browser inherits the answer.
- A generated schema that is stricter than the live server is relaxed in `@api/response-schemas` with
  the reason next to it — `/v1/meta/columns` publishes a column type the API document omits.
- A session is rendered from the server's own description of its protocol: its labels, its order, its
  value kinds. Capture points run two decoder generations, so a published path may name nothing in a
  given payload; nothing is guessed into a label, and every decoded value the description did not
  claim is shown under its own path, marked as undescribed.
- Session ids are uint64 strings. Nothing parses one, and nothing formats one as a number.
- Import aliases (declared once in `tsconfig.json`, picked up by Next, Vitest and Playwright):
  `@api/*` → `src/lib/api/*`, `@lib/*` → `src/lib/*`, `@/*` → `src/*`. Use them across folders;
  keep relative imports only inside the same folder.
- Loading, empty and error states come from `@/components/states`, and transient failures from
  `useToast` — screens never hand-roll their own. What a failure says and whether it offers a
  retry is decided once, in `@api/failure`.
- Forms are React Hook Form + zod through `@hookform/resolvers`, with the shared `Field` doing the
  labelling; the schema mirrors the API's own limits so a doomed attempt never leaves the browser.
- Values are formatted in `@lib/format` and nowhere else: timestamps are shown in UTC with the
  zone spelled out, absent values get the shared marker, and identifiers are passed through as
  strings — they are wider than a JavaScript number, so nothing may parse them.
- Unit tests live next to the code as `*.test.ts(x)`; Playwright specs live in `e2e/`.
- The e2e suite runs one worker: the API's limits are per account (three search slots, and signing
  out revokes the account's sessions), so parallel specs are not independent. A spec that starts a
  search uses the shared helper in `e2e/search-flow.ts`, which hands slots back by id.
- Conventional commits (commitlint + husky run from the repo root).

## Agentic workflow

`.claude/` carries the workflow this repo is driven with — ported from the i4f project and adapted here.

- **Rules** (`.claude/rules/`) — always in force. `00-working-boundaries` (no silent guessing, confidence
  levels), `01`–`06` (research → test statements → conflict matrix → DoR → DoD → post-implementation
  review), `07-git-boundaries` (**the agent never branches, commits or pushes**), plus coding style and
  anti-patterns.
- **Commands** (`.claude/commands/`) — the pipeline: `/spec` → `/plan` → `/implement`, plus
  `/code-review`, `/refactor`, `/optimize`, `/types`. Specs land in `specs/NNN-slug.md`, plans in
  `plans/NNN-slug.md` with the same number.
- **Agents** (`.claude/agents/`) — `architect` (where things go), `planner` (file-level plan),
  `code-reviewer` (quality and safety), `plan-verifier` (final PASS/FAIL gate, evidence or FAIL).
- **Skills** (`.claude/skills/`) — project-specific: `http-discipline` (the checks the backend scores),
  `api-layer` (server call → route handler → hook), `e2e-testing`, `tdd`. The rest are vendored from the
  skills registry into `.agents/skills/` and symlinked.
- **Hooks** (`.claude/hooks/`, wired in `.claude/settings.json`) — git writes denied, dangerous shell
  commands denied, reading files with secrets denied, and after every edit: format, related unit tests,
  and a review gate on large changesets.

Because of `07-git-boundaries`, finishing work means: verified changes in the working tree plus a
ready-to-paste commit message. The human commits.
