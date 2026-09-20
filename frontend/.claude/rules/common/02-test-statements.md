# 02 — Test Statements

## Purpose

This file formalizes the task as **observable behavioral outcomes**.

The agent must think in terms of:

- what is currently not true;
- what must become true after implementation.

This file acts as a hybrid of:

- acceptance criteria;
- behavioral test statements;
- proto test cases;
- definition of done.

If a behavior is not in this file, it is not part of the delivered change. If a behavior is in this file, it must be observably true after the MR is merged.

## Core format

Each test statement must be written in this form:

- **Current state:** NO
- **Expected state after implementation:** YES

The statement itself must describe an observable system behavior — something a QA or another human can verify without reading the code.

## Good statement criteria

A good statement:

- describes behavior, not code;
- can be verified from outside the implementation;
- focuses on outcome;
- is narrow enough to be testable;
- avoids vague wording like "properly", "correctly", or "better" unless clarified.

## Statement template

### T-001 — [Short title]

- **Statement:** After [trigger/event], [observable result] happens in [place/system area].
- **Current state:** NO
- **Expected state after implementation:** YES
- **Evidence:** [optional links to relevant indexed items]
- **Notes:** [optional]
- **Planned change summary:** [added in later pass]
- **Complexity:** Simple / Moderate / Complex

## Example

### T-001 — Application form save creates row without refresh

- **Statement:** After clicking Save on a valid Application form, the created application appears in the Applications list without requiring a full page refresh.
- **Current state:** NO
- **Expected state after implementation:** YES
- **Evidence:** E-004, E-009
- **Notes:** Confirm whether the list uses optimistic update or refetch.
- **Planned change summary:** Likely requires post-success refetch hook on the list query.
- **Complexity:** Moderate

## Coverage rule

The file should aim to cover:

- happy path behavior;
- important validation behavior;
- error or fallback behavior where relevant;
- state transitions;
- visible side effects, if they are part of the user expectation.

## Grouping suggestion

Where useful, group statements under:

- Happy path
- States and validation
- Error handling
- Integration behavior
- Permissions / visibility
- Analytics / tracking
- Regression-sensitive behavior

## Planned change summary rule

After the early research passes, each statement should get a very short implementation-oriented note:

- what likely needs to change;
- without turning the file into a full technical design document.

Keep it short. Two or three lines per statement maximum.

## Complexity rule

If a statement appears hard to satisfy because of missing contracts, architecture uncertainty, or risky side effects:

- mark it as `Complex`;
- reference the relevant blocker in `conflict-matrix.md`.

## Statement quality rule

Bad:

- "Refactor the sync logic."
- "Use a better hook."
- "The page should work."
- "Improve error handling."

Good:

- "After clicking Save on a valid form, the created entity appears in the list without requiring a full page refresh."
- "When the API returns 403, the page shows an access-related message instead of the generic error state."
- "When the user navigates back to the page after deleting an item, the deleted item does not reappear."

## Completion rule

The task is not sufficiently formalized until the majority of important expected outcomes are represented here as behavioral statements.

If you cannot phrase the change as a list of test statements, you do not yet understand the change well enough to implement it.
