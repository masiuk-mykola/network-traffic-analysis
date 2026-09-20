# 01 — Research Protocol

## Goal

Before implementation, the agent must build a structured understanding of the task using only accessible sources.

This workflow is **research-first, not code-first**.

## Primary objective

Transform a raw feature request into:

- a relevant evidence index;
- a conflict and blocker map;
- a formal list of behavioral test statements;
- a preliminary change map;
- an impact review.

Code edits come AFTER these artifacts exist. Never before.

## Required pass sequence

The agent should work in sequential passes. Each pass has defined inputs, defined outputs, and a defined exit criterion. Passes are not optional and not interchangeable.

---

### Pass 1 — Initial context gathering

**Objective.** Collect all directly relevant evidence from:

- repository structure;
- source code;
- existing tests;
- local documentation;
- Figma designs, if available.

**Required outputs:**

- initialize or update `evidence-index.md`;
- initialize or update `conflict-matrix.md`;
- initialize or update `test-statements.md`.

**Instructions.** The agent must:

1. identify relevant files, components, flows, contracts, and existing behaviors;
2. gather evidence references;
3. extract observable requirements from the task text;
4. convert the task into behavioral statements written as:
   - current state: NO
   - desired state after implementation: YES

**Exit criterion.** Every claim in the task description has either an evidence reference or a blocker entry. Nothing is left uncategorized.

**Critical.** At this stage, the agent must not invent missing requirements. Unknowns must be recorded as unknowns.

---

### Pass 2 — Blocker refinement

**Objective.** Use the evidence already collected to reduce uncertainty.

**Required outputs:**

- update `evidence-index.md`;
- update `conflict-matrix.md`;
- update `test-statements.md`.

**Instructions.** For each blocker or ambiguity, the agent should:

1. search the already-identified relevant sources again, more carefully;
2. check whether code already answers the question;
3. check whether Figma implies an expected behavior;
4. update the blocker with resolution status.

**Blocker handling rule.** Do not delete resolved blockers. Instead:

- mark them as `Resolved`;
- record how they were resolved;
- record the evidence used.

**Exit criterion.** Every blocker has either been resolved with evidence, reclassified as a complex case, or assigned to a human owner for external confirmation.

---

### Pass 3 — Per-test change analysis

**Objective.** For each test statement, provide a lightweight implementation-oriented analysis.

**Required outputs:**

- update `test-statements.md`;
- initialize or update `change-map.md`;
- update `conflict-matrix.md` with a `Complex cases` section if needed.

**Instructions.** For each test statement, the agent should add:

- a short note about what likely needs to change;
- likely files or modules;
- whether the case appears straightforward or complex.

**Complex case rule.** If a test statement requires deep unknown analysis, risky architectural changes, or unclear contracts:

- move or reference it in `conflict-matrix.md` under `Complex cases`;
- explain why it is complex;
- do not fake precision.

**Exit criterion.** Every test statement has either a change note or a Complex case entry. No test statement is left unannotated.

---

### Pass 4 — Cross-reference pass

**Objective.** Cross-link blockers, test statements, and likely change areas.

**Required outputs:**

- update `change-map.md`;
- update `conflict-matrix.md`;
- optionally update `impact-review.md`.

**Instructions.** The agent should identify:

- which components likely change;
- which contracts may be affected;
- which data flow may change;
- which dependencies need validation;
- where one blocker may partially answer another.

This pass is about system relationships, not final implementation details.

---

### Pass 5 — Finalization after user decisions

**Objective.** After the user answers remaining open questions, finalize the planning artifacts.

**Required outputs:**

- finalized `test-statements.md`;
- updated `conflict-matrix.md`;
- updated `change-map.md`;
- updated `impact-review.md`.

**Instructions.** After the user clarifies remaining decisions, the agent should:

1. update test statements according to accepted decisions;
2. preserve rejected alternatives if they matter historically;
3. mark remaining unresolved items clearly;
4. align the change map with the final intended direction.

---

### Bonus pass — Hidden consequences review

**Objective.** Think beyond the happy path.

**Required output:**

- initialize or update `impact-review.md`.

**Instructions.** The agent should list:

- adjacent areas that may regress;
- invisible assumptions likely to break;
- side effects on data flow;
- contract mismatches;
- UI state gaps;
- authorization, validation, cache, navigation, analytics, and error-handling risks where relevant.

This pass is the difference between code that ships and code that ships AND survives the next sprint.

---

## General research rules

The agent must:

- prefer evidence over intuition;
- explicitly separate fact, inference, and uncertainty;
- think in observable outcomes, not just code edits;
- keep artifacts concise, structured, and reusable;
- avoid bloating prompts with raw context when indexed references are enough.
