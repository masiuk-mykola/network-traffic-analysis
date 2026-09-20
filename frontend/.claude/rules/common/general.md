---
paths:
  - '**/*'
---

# General Rules

These rules apply to all code in this project.

## Behavior

- Do not change behavior unless explicitly asked
- Do not add features, props, or options that were not requested
- Do not refactor working code that is adjacent to the task

## Complexity

- Do not overengineer — the simplest solution that works is correct
- Do not add unnecessary abstractions (wrappers, factories, registries) for code used once
- Do not add configuration flags for behavior that should always be the same
- Three similar lines of code is better than a premature abstraction

## Readability

- Prefer simple over clever
- Keep code readable — the next developer is as important as the compiler
- Avoid nested ternaries — use `if/else` or extract to a named variable
- Avoid large functions — split at 50 lines, hard limit 100 lines
- No magic numbers — use named constants
- No unused variables — remove them

## Code hygiene

- No `console.log` in final code
- No commented-out code blocks left behind
- No TODO comments without a linked issue
- No hardcoded secrets, tokens, or environment-specific URLs

## Safety

- Validate all external input before using it
- Never trust API responses — check for expected shape
- Never render user-provided content as raw HTML
- Never store sensitive data in localStorage without understanding the security implications
