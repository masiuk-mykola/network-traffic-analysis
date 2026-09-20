# 07 — Git Boundaries

## Purpose

This file defines a hard boundary: **the agent never creates branches, never commits, and never pushes.** Those actions belong to the human, always.

This is not the default "commit only when asked" guidance — it is stricter. Even when a task feels finished and a commit looks like the obvious next step, the agent stops at the working tree and hands control back.

## What the agent must NOT do

The agent must never run (directly, in a compound command, or via a script it invokes):

- `git commit` (including `git commit --amend`)
- branch creation: `git checkout -b` / `-B`, `git switch -c` / `-C` / `--create`, `git branch <new-name>`
- `git push`
- history-writing commands that create commits: `git merge`, `git rebase`, `git cherry-pick`, `git revert`

These are also blocked mechanically by a PreToolUse hook (`.claude/hooks/block-git-writes.sh`, wired in `.claude/settings.json`). The hook is the enforcement; this rule is the intent. If the hook denies a command, that is expected — do not try to work around it.

## What the agent MAY do

- Read-only git: `git status`, `git diff`, `git log`, `git show`, `git branch` (listing only)
- Stage changes: `git add` / `git restore --staged`
- **Prepare** a commit for the human: write the changes, stage them if helpful, and print a ready-to-paste commit message so the user can commit with one step. Do **not** add a trailer naming the agent — this repo ships without one.

## Behavior at "done"

When implementation is complete and verified, the agent:

1. summarizes what changed and that it is verified (lint/type-check/tests as applicable);
2. offers a prepared commit message and/or branch name as text;
3. **waits for the user to perform the commit / branch / push themselves.**

The agent does not ask "should I commit?" as a path to committing — committing is simply not the agent's action in this repo.

## Override

This is a project-wide default. An individual who wants the agent to commit can override the hook in their own `.claude/settings.local.json` (local settings override project settings). The markdown intent here still stands unless that person also tells the agent otherwise in-session.
