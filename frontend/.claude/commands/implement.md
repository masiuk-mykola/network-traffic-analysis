---
description: Execute an implementation plan step-by-step, test-first (TDD), staying strictly in scope.
argument-hint: "[path to the plan file, e.g. plans/003-feature.md]"
---

You are executing an IMPLEMENTATION PLAN. Turn the plan below into working code — in order,
test-first, without going outside its scope.

Plan: $ARGUMENTS

## Before writing any code

1. Read the given plan **in full**, and the spec it came from (`specs/NNN-<same-slug>.md`).
2. **Gate on open questions:** if the spec still has unresolved **Open questions**, or the plan is
   ambiguous about a step, **stop and ask** — do not invent a resolution.
3. Confirm the plan's **Files to touch** and **Verification** sections are concrete. If a step has no
   clear file/action, ask before proceeding.

## How to execute

- Work through the plan's **Steps in order**. Do the smallest useful increment per step.
- For any new **deterministic logic** (retry policy, cursor handling, mappers, formatters, guards) and
  for bug fixes, follow the `tdd` skill: **failing test first → minimal code to green → refactor.**
  Negative/edge cases are mandatory, not just the happy path.
- UI rendering and navigation are proven by Playwright **e2e** (`e2e/`), not by unit tests.
- Follow this repo's conventions — do not invent parallel patterns:
  - API calls — `rawFetch` → `callApi` → a route handler under `src/app/api/**` → a React Query hook.
    Nothing in the browser touches `CAPTURE_API_URL`. Reuse the `api-layer` skill.
  - HTTP behaviour — the rules in the `http-discipline` skill and `SETUP.md` section 5a are
    requirements, not suggestions; the backend scores them.
  - Types — from the generated `src/lib/api/schema.d.ts` (`npm run api:types`), never hand-written,
    never edited by hand.
  - Components — server by default, `'use client'` only on the leaf that needs it; Radix primitives +
    Tailwind + `cn()`.
  - Every fetching surface ships its loading, empty and error state in the same step as the happy path.

## Scope discipline

- Touch only what the plan's **Files to touch** lists. If you discover a needed change outside that
  set, **note it and ask** rather than silently expanding scope.
- Do not refactor adjacent working code that the task does not require.
- Never edit anything under `../backend` — it is given and fixed.

## Verify before you call it done

- Run, at minimum: `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, and
  `npm run test:e2e` when e2e is in scope.
- If the change touched the data layer, run the backend's own verdict with the API up and the flow
  exercised: `cd ../backend && PYTHONPATH=src .venv/bin/python -m capture_api report` — no FAIL.
- Walk the plan's **Verification** table: for each acceptance criterion, show how it is now satisfied
  (a passing test, a driven flow, an observed result) — evidence, not claims.
- Report honestly: if a step is incomplete or a check was skipped, say so.

## Hand-off (do not commit)

Per repo git boundaries, **do not commit or push.** When the plan is implemented and verified:

1. Summarize what changed against the plan's Files to touch, and flag anything that diverged.
2. Print a ready-to-paste commit message (conventional commits, no agent trailer).
3. Stop there. The human commits.
