#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash) — denies git write operations so that branch
# creation, commits, and pushes stay the human's job. See .claude/rules/common/07-git-boundaries.md.
#
# Reads the hook JSON from stdin, inspects tool_input.command, and on a blocked
# git operation prints a PreToolUse "deny" decision and exits 0. Anything else
# exits 0 with no output (default allow).
#
# Blocked: git commit (+ --amend), branch creation (checkout -b/-B, switch -c/-C/--create,
#          git branch <name>), push, merge, rebase, cherry-pick, revert.
# Allowed: status, diff, log, show, branch (listing), add / restore.

# The hook JSON arrives on stdin; capture it before the heredoc takes over stdin
# (python reads its program text from the heredoc, the payload comes via env var).
HOOK_JSON="$(cat)" python3 <<'PY'
import sys, json, shlex, os

REASON = (
    "Blocked by .claude/rules/common/07-git-boundaries.md: in this repo the agent "
    "never creates branches, commits, or pushes — the user does that manually. "
    "Stage changes and hand over a ready-to-paste commit message instead."
)

def allow():
    sys.exit(0)

def deny(detail):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{detail} {REASON}"
        }
    }))
    sys.exit(0)

try:
    payload = json.loads(os.environ.get("HOOK_JSON", "") or "{}")
except Exception:
    allow()  # can't parse → don't block

command = (payload.get("tool_input") or {}).get("command", "")
if not command:
    allow()

try:
    tokens = shlex.split(command, comments=True)
except ValueError:
    # Unbalanced quotes etc. — fall back to a naive split so we still inspect it.
    tokens = command.split()

SEPARATORS = {"&&", "||", "|", ";", "&", "(", ")", "{", "}", "\n"}
# git global options that consume the following token as their value.
GLOBAL_OPTS_WITH_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
# Subcommands that are always blocked.
BLOCKED_SUBCMDS = {"commit", "push", "merge", "rebase", "cherry-pick", "revert"}
# branch inspection flags that make `git branch` read-only.
BRANCH_INSPECT_FLAGS = {
    "-l", "--list", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose",
    "--show-current", "--contains", "--no-contains", "--merged", "--no-merged",
    "--points-at", "--format", "--color", "--no-color", "--column", "--no-column", "--sort"
}

# Split the command into pipeline segments and inspect each git invocation.
segment = []
segments = []
for tok in tokens:
    if tok in SEPARATORS:
        if segment:
            segments.append(segment)
            segment = []
    else:
        segment.append(tok)
if segment:
    segments.append(segment)

for seg in segments:
    # Find the `git` executable position (skip leading env assignments like FOO=bar).
    gi = None
    for i, tok in enumerate(seg):
        base = os.path.basename(tok)
        if base == "git":
            gi = i
            break
        if "=" in tok and not tok.startswith("-"):
            continue  # env assignment before the command
        # first real word isn't git → not a git invocation
        break
    if gi is None:
        continue

    args = seg[gi + 1:]

    # Skip git global options to reach the subcommand.
    j = 0
    while j < len(args):
        a = args[j]
        if a in GLOBAL_OPTS_WITH_VALUE:
            j += 2
            continue
        if a.startswith("-"):
            j += 1
            continue
        break
    if j >= len(args):
        continue  # bare `git` / only global opts
    subcmd = args[j]
    rest = args[j + 1:]

    if subcmd in BLOCKED_SUBCMDS:
        deny(f"Refused `git {subcmd}`.")

    if subcmd == "checkout":
        if any(r in ("-b", "-B") for r in rest):
            deny("Refused branch creation via `git checkout -b`.")

    if subcmd == "switch":
        if any(r in ("-c", "-C", "--create") or r.startswith("--create") for r in rest):
            deny("Refused branch creation via `git switch -c`.")

    if subcmd == "branch":
        has_inspect = any(r in BRANCH_INSPECT_FLAGS or r.startswith("--sort") or r.startswith("--format")
                          for r in rest)
        positionals = [r for r in rest if not r.startswith("-")]
        create_flags = any(r in ("-m", "-M", "-c", "-C") for r in rest)
        if not has_inspect and (positionals or create_flags):
            deny("Refused branch creation/rename via `git branch`.")

allow()
PY
