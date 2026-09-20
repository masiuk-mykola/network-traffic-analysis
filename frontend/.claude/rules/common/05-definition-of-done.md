# 05 — Definition of Done

## Purpose

This file defines the **pre-merge gate**. It answers the single question:

> Is this change ready to ship, or are we shipping it because we are tired?

The Definition of Done (DoD) is the mirror of the Definition of Ready. DoR governs what the agent is allowed to start; DoD governs what the agent is allowed to merge.

The DoD is the hardest gate to enforce because at this point the work feels finished. The work is finished only when the checklist passes — not when the code compiles.

## When this gate runs

After the agent has generated an implementation and the human reviewer has done the first pass. Before clicking Merge.

The reviewer walks the checklist below and decides:

- `DONE` — the change may be merged;
- `NEEDS FIXES` — the change is real but specific items below have not yet passed;
- `REJECTED` — the change does not solve the task and must be redone.

## The checklist

Every item must be **true** before a change is marked Done.

### Behavior

- [ ] Every test statement from `02-test-statements.md` is observably true in the running system.
- [ ] No test statement was silently removed during implementation.
- [ ] If new test statements were discovered during implementation, they are added to the file with status and outcome.
- [ ] Edge cases (empty / loading / error / permission denied) have been manually verified, not just assumed to work.

### Code grounding

- [ ] The change reuses existing components and patterns where appropriate.
- [ ] No parallel architecture was introduced where an existing one would have worked.
- [ ] Refactors not required by the task were either reverted or moved to a separate task.

### Conflict matrix closure

- [ ] Every blocker that was resolved during implementation is marked `Resolved` in `conflict-matrix.md` with resolution, evidence, and date.
- [ ] No blocker silently disappeared. If a blocker was decided in conversation, the decision is captured in the file.
- [ ] Newly discovered ambiguities are logged before merge, even if they were not on the original blocker list.

### Change map alignment

- [ ] `change-map.md` reflects what actually changed, not what was originally planned.
- [ ] Files touched outside the planned change map have a justification (in-line note or blocker entry).

### Impact review

- [ ] `impact-review.md` lists what could regress and what was checked.
- [ ] Items marked "checked" were actually checked, not assumed.
- [ ] Unchecked items are explicitly carried into follow-up work.

### Code quality (the boring layer)

- [ ] The MR passes the project's automated checks (lint, type-check, unit tests, CI).
- [ ] Any test that was disabled has a TODO and an owner.
- [ ] Console logs / debug prints / commented-out blocks introduced during the run have been removed.

### Reviewability

- [ ] The MR description points to the relevant test statements and resolved blockers.
- [ ] The reviewer can answer "why did the implementation choose X over Y?" by reading the matrix and the change map, not by guessing.

### Reversibility

- [ ] If this change has to be reverted, the revert path is clear (single MR, no hidden dependencies).

## Failure modes this prevents

- **"It works on my machine"** — DoD requires running system verification, not just compile success.
- **"The original blocker was something else, but it works now"** — DoD requires explicit closure of every matrix entry.
- **"I cleaned up some stuff on the way"** — DoD requires scope discipline at merge time, not only at ready time.
- **"We can fix that in a follow-up"** — DoD requires the follow-up to be filed as a real task, not lived in someone's head.

## How to use it

1. Open the MR.
2. Walk the checklist top to bottom.
3. Mark the MR `DONE`, `NEEDS FIXES`, or `REJECTED`.
4. Only `DONE` MRs are merged. `NEEDS FIXES` go back to the implementation loop with the failing items listed.

## DoD vs. QA

These are not the same.

- DoD is owned by the implementer + reviewer. It is the **structural** check: did the artifacts close, did the scope hold, did the contracts get respected.
- QA is owned by the QA function. It is the **behavioral** check: does the running system actually behave the way the test statements describe.

A change can pass DoD and still fail QA — and that is fine, that is what QA is for. A change should never pass QA without passing DoD first.

## DoD exception rule

There are no DoD exceptions for production-targeted changes. None.

Hotfixes are an apparent exception. They are not. A hotfix has its own minimal DoR and DoD adapted to the urgency — but they still exist, and they are still checked. The cost of skipping the DoD on a hotfix is higher than the cost of writing one.
