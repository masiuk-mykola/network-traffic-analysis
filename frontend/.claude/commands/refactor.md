# /refactor

Refactor the selected code. Keep behavior identical unless explicitly told otherwise.

## What to do

1. Read the target file(s) fully before touching anything
2. Identify the specific problems: duplication, deep nesting, large functions, unclear names, mixed responsibilities
3. Apply targeted fixes — do not rewrite code that is not part of the problem
4. Verify the refactored version is functionally equivalent

## Rules

- Do NOT change behavior — only structure and clarity
- Do NOT add new features, error handling, or validations that did not exist
- Do NOT rename things across the codebase unless asked
- Do NOT refactor working adjacent code just because it could be better
- Keep the diff minimal and focused

## Techniques to apply

- Extract repeated logic into a named function or hook
- Replace nested conditions with early returns
- Split large components (> 200 lines) into smaller focused ones
- Move inline logic out of JSX into named variables or handlers
- Replace magic numbers/strings with named constants
- Rename variables and functions to reflect their actual purpose

## Output

Show only the changed files. Briefly state what changed and why — one sentence per change.
