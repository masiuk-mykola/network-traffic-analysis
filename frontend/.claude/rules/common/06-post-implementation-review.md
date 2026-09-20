# 06 — Post-Implementation Review

## Purpose

This file defines the **post-merge learning gate**. It answers two questions:

> What did this run teach us about the system?
> What did this run teach us about the rulesets?

The Post-Implementation Review (PIR) is the only mechanism that makes the ruleset improve over time. Without it, the rulesets calcify into yesterday's lessons.

## When this gate runs

After merge. Specifically:

- For features: within one week of merge, or after the first user feedback cycle (whichever is sooner).
- For bug fixes: after the fix has been live long enough to confirm the bug did not return (usually 1–2 sprints).
- For risky / complex changes: a scheduled PIR within 48 hours, even if there is nothing to report yet.

## The structure

A PIR is a short note (one screen of text, not a document) with five sections.

### 1. What the change actually did

- What test statements passed in production?
- Were any of them later contradicted by user behavior?
- Did the change cause any side effects that were not in `impact-review.md`?

### 2. What broke

- Did anything regress?
- Did QA find issues that DoD missed? If yes — why did DoD miss them?
- Did production find issues that QA missed? If yes — what was the QA gap?

### 3. What surprised us

- Was there a blocker that turned out to matter more than its confidence level suggested?
- Was there a blocker that turned out not to matter at all? (Equally important.)
- Did the agent reuse the right pattern, or did it invent one despite the rules?
- Did the rulesets prevent a failure mode you noticed mid-run?

### 4. What the rulesets should learn

This is the most important section. Concrete proposals to update one of:

- `00-working-boundaries.md`
- `01-research-protocol.md`
- `02-test-statements.md`
- `03-conflict-matrix.md`
- `04-definition-of-ready.md`
- `05-definition-of-done.md`
- (or this file itself)

Each proposal is one sentence + the file + the line/section to change.

If there are no proposals, write "No ruleset updates" explicitly. The discipline is to **decide** that nothing should change, not to skip the question.

### 5. Open follow-ups

- What was deferred?
- What new blockers were discovered?
- What is still on the team's plate as a consequence of this change?

## Example PIR

> **PIR — Complaint Details fix (MR !3421)** — 2026-04-22
>
> **What the change actually did:** T-001 (no error on Withdrawn status) passes in prod. T-002 (reduced field set on Withdrawn) also passes. No user reports of regression.
>
> **What broke:** QA initially missed that the loading state on the new branch was unstyled. Caught in second QA pass. DoD checklist item "edge cases manually verified" was checked too quickly.
>
> **What surprised us:** The same status guard pattern existed in two places in the codebase but with slightly different signatures. The agent reused one but not the other, leaving the second to be cleaned up later.
>
> **What the rulesets should learn:** Add to `04-definition-of-ready.md` Architecture grounding section: "If a pattern exists in multiple variants in the codebase, note which one is the canonical version." This would have caught the agent's choice as a blocker entry.
>
> **Open follow-ups:** Clean up the second variant of the status guard (filed as MR !3445).

## Why this gate exists in its own file

The PIR is the only place where the rulesets are allowed to grow. If you skip it, the rulesets stay static — and a static ruleset is a ruleset that is wrong about something it has not yet learned.

The ten-minute PIR is the cheapest engineering investment in this whole framework. The cost of skipping it is paid in repeated failures that no one connects to a common cause.

## PIR vs. retrospective

These overlap but are not the same.

- A retrospective is team-level, recurring, broad. It asks "how are we working together?"
- A PIR is change-level, on-demand, narrow. It asks "what did this specific change teach us?"

A team can have retrospectives without PIRs. A team running agentic engineering at scale **cannot** skip PIRs — because the rulesets that govern the agents are themselves the artifact being learned.

## PIR exception rule

The only exception is trivially small changes (typo fixes, copy updates with no logic change). For these, the PIR collapses to a single line: "Trivial — no PIR needed". Even that line is written down. Skipping is not allowed; collapsing is allowed.
