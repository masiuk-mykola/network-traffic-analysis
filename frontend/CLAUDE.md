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
npm run api:types           # regenerate src/lib/api/schema.d.ts from ../backend/openapi.json
```

The API must be up for anything past the skeleton:
`cd ../backend && uv sync --no-install-project && PYTHONPATH=src .venv/bin/python -m capture_api serve`
(plain `uv sync` fails — the packaging metadata points at a `README.md` that is not in the archive).

## Architecture

The API has CORS off and takes a bearer token, so the browser never talks to it directly.

- `src/lib/api/client.ts` — raw fetch with timeouts, `ApiError`, `Retry-After` parsing. No retries,
  no refresh.
- `src/lib/api/session-store.ts` — access and refresh tokens, keyed by an opaque session id.
  Refresh is single-flight per token family.
- `src/lib/api/server.ts` — `callApi()`: authorized call, one refresh and one replay on a 401.
- `src/app/api/**` — route handlers. `/api/auth/login` hands back only the profile,
  `/api/capture/[...path]` proxies GETs. Everything token-shaped stays behind `server-only`.

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
- Import aliases (declared once in `tsconfig.json`, picked up by Next, Vitest and Playwright):
  `@api/*` → `src/lib/api/*`, `@lib/*` → `src/lib/*`, `@/*` → `src/*`. Use them across folders;
  keep relative imports only inside the same folder.
- Unit tests live next to the code as `*.test.ts(x)`; Playwright specs live in `e2e/`.
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
