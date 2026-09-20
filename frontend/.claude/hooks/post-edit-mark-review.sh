#!/usr/bin/env bash
# PostToolUse hook (matcher: Edit|Write|MultiEdit) — marks that the working tree
# was modified since the last code review, so the Stop hook knows to require one.
# See .claude/hooks/stop-code-review.sh and the plan for the full flow.
#
# Reads (and discards) the hook JSON from stdin, then touches a sentinel file.
# Always exits 0 — this hook never blocks anything.

cat >/dev/null 2>&1 || true

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
mkdir -p "$PROJECT_DIR/.claude" 2>/dev/null || true
touch "$PROJECT_DIR/.claude/.needs-review" 2>/dev/null || true

exit 0
