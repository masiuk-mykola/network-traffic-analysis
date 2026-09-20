#!/usr/bin/env bash
# Stop hook — before Claude hands control back, require a code review of the
# uncommitted changes IF files were edited since the last review.
#
# A hook cannot invoke a slash command directly. Instead this hook returns a
# Stop "block" decision whose `reason` instructs the agent to perform the review
# described in .claude/commands/code-review.md, in the same session.
#
# Trigger: the sentinel file .claude/.needs-review (created by the PostToolUse
# hook post-edit-mark-review.sh after any Edit/Write/MultiEdit) AND more than
# REVIEW_FILE_THRESHOLD (10) files changed in the working tree (git status,
# ignored files excluded). Small changesets skip the gate.
#
# Loop protection (triple):
#   1. the sentinel is removed BEFORE blocking, so the next Stop won't see it;
#   2. stop_hook_active == true means we're already in a stop-hook continuation
#      → allow the stop instead of blocking again;
#   3. Claude itself overrides after 8 consecutive blocks without progress.

# Capture the hook JSON from stdin before the heredoc takes over stdin.
HOOK_JSON="$(cat)" python3 <<'PY'
import sys, json, os, subprocess

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
SENTINEL = os.path.join(PROJECT_DIR, ".claude", ".needs-review")
# Only force a review for large changesets. A trivial 1–2 file edit doesn't warrant
# the gate; a sweeping change (> 10 files touched) does.
REVIEW_FILE_THRESHOLD = 10

REASON = (
    "Before finishing, review the uncommitted changes per the instructions in "
    ".claude/commands/code-review.md (git diff --name-only HEAD → check "
    "security/quality/best-practices for each changed file). "
    "Once the review is done, just finish your response — this hook won't fire again."
)

def allow():
    sys.exit(0)

try:
    payload = json.loads(os.environ.get("HOOK_JSON", "") or "{}")
except Exception:
    allow()  # can't parse → don't block

# 2. Already continuing from a prior stop-hook block → let the agent stop.
if payload.get("stop_hook_active") is True:
    allow()

# Trigger only when files were actually edited since the last review.
if not os.path.exists(SENTINEL):
    allow()

# 1. Remove the sentinel first so the next Stop won't re-trigger.
try:
    os.remove(SENTINEL)
except OSError:
    pass

# Only gate large changesets. Count changed files in the working tree
# (git status --porcelain: staged + unstaged + untracked, ignored excluded — so
# edits to .claude/ or claude-report.md don't count). Fail-open on any git error.
try:
    out = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10
    )
    changed_files = [ln for ln in out.stdout.splitlines() if ln.strip()]
except Exception:
    changed_files = []

if len(changed_files) <= REVIEW_FILE_THRESHOLD:
    allow()

print(json.dumps({"decision": "block", "reason": REASON}))
sys.exit(0)
PY
