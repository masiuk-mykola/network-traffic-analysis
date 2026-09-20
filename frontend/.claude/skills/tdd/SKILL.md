---
name: tdd
description: Use when implementing any new logic or fixing a bug in this repo — write a FAILING unit test (Vitest) derived from the acceptance criteria first, then the minimal code to go green, then refactor. Mandatory for pure logic (retry policy, cursor and pagination handling, mappers, formatters, guards). Covers negative and edge cases, not just the happy path.
---

# TDD — red → green → refactor

A test is a **machine-checkable contract** for a behavior. In this repo the agent does not get to skip
it: new logic starts from a failing test, and the test — not a prose claim — is what proves the
behavior is done.

## When this applies

- Any new pure logic: `src/lib/**` (retry policy, `Retry-After` parsing, cursor handling, formatters,
  guards, mappers over API payloads).
- Any bug fix: first write the test that **reproduces** the bug (red), then fix it.
- Rendering, navigation and the server boundary are out of scope here — those are covered by Playwright
  under `e2e/`, not by this unit loop.

## The loop

### 1. RED — write a failing test first

- Turn **each** acceptance criterion (from `specs/` if a spec exists, else from the task text) into at
  least one test case.
- Co-locate the test next to the code: `foo.ts` → `foo.test.ts`.
- Use explicit imports — this repo does not enable Vitest globals:
  ```ts
  import { describe, expect, it } from 'vitest'

  import { parseRetryAfter } from './client'
  ```
- Run it and **watch it fail for the right reason**: `npm run test` (or `npm run test:watch`). A test
  that passes before you write the code is not testing anything.

### 2. GREEN — minimal code to pass

- Write the smallest change that makes the failing test pass. No extra features, no speculative
  options, no unrelated refactors.
- Keep going until green: `npm run test`.

### 3. REFACTOR — clean up under a green bar

- Improve naming and structure with the tests still passing. Re-run after each step.

## What a good test looks like here

- One behavior per `it`, named in English for what it guarantees:
  `it('does not retry 4xx')`, not `it('works')`.
- Cover the negative and edge cases that the backend actually produces: a 429 with an HTTP-date
  `Retry-After`, a 503 under `--chaos storm`, a 401 mid-flight, an empty page of results, a cursor that
  is an opaque string, a uint64 session id that must stay a string.
- No network in unit tests. Stub `fetch` or pass fakes; the real API is exercised by e2e.
- Never assert on a snapshot of an entire object where one field is the point.

## Definition of done for this loop

`npm run test` green, and the new test fails if you revert the implementation. If you cannot make it
fail by reverting, the test is not testing the behavior.
