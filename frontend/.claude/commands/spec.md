---
description: Turn a task into a short spec (what/why, not how) and save it to a file.
argument-hint: "[task description, or a section of the task README]"
---

You are writing a SHORT spec for the task below. A spec answers WHAT and WHY, not HOW (the
implementation plan is a separate step, /plan). Keep it concise: half a page.

Task: $ARGUMENTS

## Before writing

- **Source of requirements.** The product requirements for this repo live in `../README.md` (the task
  as handed over). If `$ARGUMENTS` is plain text, work from the text, but reconcile it with that file
  and say when they disagree.
- **Ground it in real code and in the API.** Read the relevant parts of the project so the spec
  reflects the actual state, not guesses. Landmarks:
  - `src/lib/api/` — the server-side API layer (client, session store, `callApi`)
  - `src/app/api/**` — route handlers the browser calls
  - `src/app/**` — pages (`/login`, `/search`, `/sessions/[id]`)
  - `../backend/openapi.json` — the API contract (methods, paths, required fields); `/docs` when the
    server is up
  - the `http-discipline` skill — the HTTP behaviour the backend scores
- **Do not invent ambiguity.** Anything uncertain goes into "Open questions", not into requirements.

## Spec structure (use exactly this order and these headings)

- **Context** — why this change, what problem or need it addresses, what prompted it.
- **Goals / Non-goals** — what is in scope and what is deliberately out of scope.
- **Requirements** — behavioral requirements (WHAT the system must do), including what the user sees
  while data is loading, when there is none, and when it fails.
- **Acceptance criteria** — verifiable statements, one test derivable from each (form:
  "current: NO → expected: YES", observable from outside the code).
- **Open questions** — anything not confirmed by code, the API schema, or the task text.

The spec must contain **no** file, function, hook, or endpoint names — that is the plan level (/plan).

## Then save the file

1. Look at the existing files in `specs/` and take the next free three-digit `NNN` (if empty → `001`).
2. Make a short kebab-case slug from the essence of the task.
3. Write the spec to `specs/NNN-<short-slug>.md`.
4. Print the path of the created file and, on a separate line:
   `Next step: /plan specs/NNN-<slug>.md`
