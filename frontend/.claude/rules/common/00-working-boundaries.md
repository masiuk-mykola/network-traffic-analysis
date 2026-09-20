# 00 — Working Boundaries

## Purpose

This repository uses a structured research-first workflow for AI-assisted implementation.

The agent must prepare context before proposing or implementing changes. This file defines the agent's **epistemic boundaries**: what it is permitted to use as evidence, what it must declare as unknown, and how it must behave when the truth is unavailable.

This is the file that everything else depends on.

## Available context sources

The agent may use:

- the repository code itself;
- local project files and documentation inside the repo;
- Figma designs, if Figma access is available through configured tools;
- user-provided text in the current prompt.

The agent must NOT use:

- generic product-pattern assumptions when project-specific evidence is missing;
- external web content unless the user explicitly attaches it;
- inference from prior conversations the agent does not have access to.

## Required behavior under missing context

When information is not available from code, repo docs, Figma, or user-provided text, the agent must:

1. explicitly mark the gap;
2. record it as a blocker, ambiguity, or missing decision in `conflict-matrix.md`;
3. avoid inventing facts;
4. continue best-effort analysis using only accessible evidence.

## Operating principle

The agent should think in this order:

1. What is the task asking to change in observable system behavior?
2. What evidence inside the repo or Figma supports that interpretation?
3. What is still unknown?
4. What must become true after implementation?
5. Which parts of the system are likely affected?

This order is deliberate. Behavior first. Evidence second. Unknowns third. Outcomes fourth. Affected surface fifth. Skipping a step always produces worse output.

## Default output artifacts

During research and planning, the agent should maintain these artifacts:

1. `evidence-index.md`
2. `conflict-matrix.md`
3. `test-statements.md`
4. `change-map.md`
5. `impact-review.md`

These are not optional. They are how the agent's reasoning becomes auditable.

## Truthfulness rule

If something cannot be confirmed from available sources, the agent must say one of:

- "not found in accessible sources";
- "cannot verify with current tooling";
- "requires user or external owner confirmation".

It must not infer certainty where only probability exists. "Probably works this way" is not a statement of fact. It is a blocker.

## Confidence language standard

The agent must use one of three confidence levels in any claim that depends on evidence:

- **High** — directly supported by code, design, or explicit user statement.
- **Medium** — inferred from one or two related sources, with reasonable but not direct support.
- **Low** — plausible but unsupported. Must be flagged as a blocker.

"I think" and "probably" are not acceptable replacements for an explicit confidence level.

## Scope discipline

The agent must stay focused on the current task and avoid:

- broad architectural rewrites without evidence;
- unrelated cleanup;
- speculative refactors not required by the task;
- assumptions based on generic product patterns when project-specific evidence is missing.

If the agent notices a related issue that is out of scope, it must log it in `conflict-matrix.md` under "Out of scope observations" — not act on it.

## No silent guessing (primary rule)

This is the most important rule in the entire ruleset.

If the agent does not know something and proceeds anyway without flagging the gap, the entire workflow breaks. Every downstream artifact becomes unreliable. Every downstream MR becomes a risk.

When in doubt, the agent stops and writes the unknown into `conflict-matrix.md`. It does not guess. It does not assume. It does not "fill in the blanks".
