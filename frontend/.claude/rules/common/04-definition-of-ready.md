# 04 — Definition of Ready

## Purpose

This file defines the **pre-execution gate**. It answers the single question:

> Is this task ready for the agent to start implementing, or do we need more research first?

The Definition of Ready (DoR) exists because most "AI did a bad job" stories are actually "I told the agent to start before the task was understood". This file prevents that.

## When this gate runs

After research passes (`01-research-protocol.md`) and before any code is generated.

A human reviews the produced artifacts against the checklist below and decides:

- `READY` — the agent may proceed to implementation;
- `NOT READY` — the agent must run another research pass first;
- `BLOCKED` — the task requires an external decision before any agent work continues.

## The checklist

Every item must be **true** before a task is marked Ready.

### Context

- [ ] `evidence-index.md` lists the files, components, and flows the agent has identified as relevant.
- [ ] If Figma was available, the relevant frames are referenced in the evidence index.
- [ ] No "I think this file is involved" entries — every evidence item is concrete and verifiable.

### Behavior

- [ ] `test-statements.md` contains at least one statement covering the happy path.
- [ ] Edge cases that matter for the user are represented as separate statements (empty, loading, error, permission, regression-sensitive).
- [ ] No statement uses vague language ("properly", "correctly", "better") without clarification.
- [ ] Every statement is in the `current state: NO → expected state: YES` form.

### Uncertainty

- [ ] All known blockers are logged in `conflict-matrix.md` with status, confidence, and suggested owner.
- [ ] No high-confidence **Open** blocker remains that would change the implementation direction if resolved differently.
- [ ] All **Open** blockers tagged `Medium`/`High` confidence have been escalated to the right owner (user, designer, product, backend).
- [ ] Blockers explicitly marked `Accepted risk` or `Out of scope` have a one-line rationale.

### Scope

- [ ] The scope is described in observable outcomes, not in implementation intentions.
- [ ] Adjacent areas the agent must NOT touch are explicitly listed.
- [ ] Refactor-only scope is either justified or rejected.

### Architecture grounding

- [ ] If the change touches an existing pattern, the pattern's location is referenced in `evidence-index.md`.
- [ ] If the change introduces a new pattern, the rationale is captured as a blocker entry (`Should this be a new pattern or reuse X?`).

## Failure modes this prevents

- **AI invents a component that already exists** — the evidence index would have caught it.
- **AI ships a behavior that contradicts Figma** — the test statements would have caught it.
- **AI silently resolves an ambiguity wrong** — the conflict matrix would have blocked execution until the owner answered.
- **AI refactors unrelated code** — the explicit "do not touch" list would have prevented it.

If any of these happen, the failure is almost always a DoR violation, not an AI failure.

## How to use it

1. Open the task.
2. Run the research passes from `01-research-protocol.md`.
3. Open this file and walk the checklist top to bottom.
4. Mark the task `READY`, `NOT READY`, or `BLOCKED`.
5. Only `READY` tasks proceed to code generation.

## DoR exception rule

There are no DoR exceptions for production-targeted changes.

For exploratory spikes that will not be merged, the DoR can be reduced to: "Test statements exist + scope is clear + you accept the result will be thrown away". Document the exception in the spike's task description.

## Why this exists in its own file

The DoR is the moment of highest cognitive cost. It is also the moment of highest leverage. Putting it in its own file makes the gate explicit, the checklist concrete, and the responsibility visible.

A skipped DoR is invisible. A skipped step in a file is not.
