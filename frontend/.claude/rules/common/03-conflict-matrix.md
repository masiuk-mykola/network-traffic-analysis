# 03 — Conflict Matrix

## Purpose

This file tracks:

- contradictions;
- ambiguities;
- missing decisions;
- unresolved blockers;
- resolved blockers with their resolution evidence;
- complex cases that need extra attention.

Without this file, all uncertainty gets buried in commit messages, MR threads, or silent assumptions inside the code. This file is where uncertainty becomes visible.

## Core principle

A blocker is not just a question.

A blocker should be documented as **structured uncertainty** — evidence, sources, current state, suggested owner, and status all in one place.

## Entry structure

Each blocker entry should include:

1. blocker ID;
2. statement of uncertainty or contradiction;
3. source A says X;
4. source B says Y;
5. code currently does Z;
6. confidence level;
7. suggested resolution owner;
8. status.

## Status options

Use one of:

- `Open`
- `Partially resolved`
- `Resolved`
- `Accepted risk`
- `Out of scope`

## Required categories

The file should usually contain these sections:

- Contradictions
- Ambiguities
- Missing decisions
- External validation needed
- Complex cases
- Resolved blockers history
- Out of scope observations

## Example entry

### B-003 — Empty state ownership is unclear

- **Type:** Ambiguity
- **Statement:** It is unclear whether the empty state should be rendered by the page container or by the table component.
- **Source A:** Figma shows the empty state as part of the page-level layout.
- **Source B:** Existing code handles empty rows inside the table component.
- **Code currently does:** The table renders a local fallback row instead of a page-level empty state.
- **Confidence:** High (about the contradiction itself)
- **Suggested resolution owner:** Design lead / frontend owner
- **Status:** Open

## Resolved blocker rule

Never delete a blocker after resolution.

Instead, keep it and add:

- `Resolution`;
- `Resolved by`;
- `Evidence used`;
- `Resolved at`.

Why? Because future questions about "why did we do it this way" are answered by historical blockers, not by reading code. Code shows _what_. Resolved blockers show _why_.

## Example resolved addition

- **Resolution:** Treat empty state as page-level responsibility.
- **Resolved by:** Design lead decision
- **Evidence used:** Task clarification from 2026-04-12
- **Resolved at:** 2026-04-13

## Complex case rule

When something appears implementable but structurally risky, list it under `Complex cases`.

Each complex case should explain:

- why it is hard;
- which areas it may affect;
- whether a simpler fallback exists.

## Confidence standard

Confidence should reflect evidence quality, not optimism.

Use:

- `High` — two or more independent sources agree, or one direct authoritative source (code that already does it, user statement).
- `Medium` — one indirect source or strong inference from context.
- `Low` — plausible but unsupported. Should rarely be acted on without escalation.

## Ownership rule

Suggested owner is not always the user.

Possible owners:

- User
- Designer
- Frontend owner
- Backend owner
- Product owner
- QA
- Unknown external owner

Because external systems are not connected, unresolved cross-team assumptions should usually be assigned to a human owner.

## No silent guessing

If a contradiction cannot be resolved with accessible evidence, the agent must preserve it in this file and proceed carefully.

The temptation to silently pick one interpretation and ship is the single most common reason AI-assisted MRs get reverted. This file exists specifically to prevent that.
