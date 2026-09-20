---
description: Turn a spec file into an implementation plan (how) and save it to a separate file.
argument-hint: "[path to the spec file, e.g. specs/003-feature.md]"
---

You are writing an IMPLEMENTATION PLAN from the spec file below. A plan answers HOW.

Spec: $ARGUMENTS

## Steps

1. Read the given spec **in full**. If it has unresolved **Open questions**, stop and ask the user —
   **do not invent** a resolution.
2. Read the real code the change will touch. Follow this project's conventions:
   - API calls — `src/lib/api/client.ts` (`rawFetch`) → `src/lib/api/server.ts` (`callApi`) → a route
     handler under `src/app/api/**` → a React Query hook. The browser never calls the API directly.
   - Types — `components['schemas'][...]` from the generated `src/lib/api/schema.d.ts`; regenerate with
     `npm run api:types` when the contract moved.
   - Pages — `src/app/<route>/page.tsx`, server components by default, `'use client'` only where
     interactivity requires it.
   - UI — Radix primitives + Tailwind + `cn()` from `src/lib/utils.ts`.
   - Verify the contract against `../backend/openapi.json`, and the scored behaviour against the
     `http-discipline` skill.

## Build the plan with these sections

- **Files to touch** — real paths in THIS project + what exactly changes in each.
- **Steps** — in order, each tied to a concrete file/action (not a restatement of requirements).
- **Risks** — races (refresh, logout, cancelled searches), cursor/pagination edge cases, React Query
  cache and invalidation, duplicate requests, retry/`Retry-After` handling, token leakage, chaos
  profiles (`storm`, `expiring-tokens`).
- **Verification** — a table: each acceptance criterion from the spec → how exactly we prove it. Use
  `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`,
  `npm run test:e2e`, and — when the data layer moved — `capture-api report` with no FAIL.

## Self-check

If you strip the headings, the plan must read **differently** from the spec. If it reads the same, it
is a restatement of requirements — redo it (a plan is about files, steps, and risks, not about
"what/why").

## Then save the file

Write the plan to `plans/NNN-<same-slug>.md` — the **same NNN and slug** as the spec. Print the path of
the created file and remind the reader: the plan should be read by a human **before** implementation.
Do not start a multi-file feature without a plan file that has been read.
