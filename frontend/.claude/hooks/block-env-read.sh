#!/usr/bin/env bash
#
# PreToolUse hook (matcher: Bash).
# Reads the tool-call JSON from stdin and blocks shell commands that would read
# a .env file (cat, grep, head, sed, cp, ... anything at all).
#   exit 2 = BLOCK (reason on stderr)   exit 0 = allow
#
# The Read tool is blocked separately by the permissions.deny rules in
# .claude/settings.json; this hook closes the shell loophole.
#
# Approach: scrub the known-safe forms out of a working copy of the command,
# then block if any .env path token survives. That way new read verbs are
# covered by default instead of needing a verb allow-list.

set -uo pipefail

# --- Forms that are allowed to mention a .env path. --------------------------
ALLOWED_PATTERNS=(
  '\.env\.example'                      # tracked, holds variable names only
  '--env-file(-if-exists)?[= ][^[:space:]]*'  # node --env-file=... loads, never prints
)
# -----------------------------------------------------------------------------

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
else
  cmd=$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p')
fi

[ -z "$cmd" ] && exit 0

# Fast path: nothing that looks like a .env path at all.
printf '%s' "$cmd" | grep -Fq '.env' || exit 0

# Remove the allowed forms, then see whether a .env token remains.
scrubbed=$cmd
for pat in "${ALLOWED_PATTERNS[@]}"; do
  scrubbed=$(printf '%s' "$scrubbed" | sed -E "s|$pat||g")
done

if printf '%s' "$scrubbed" | grep -Eq '(^|[^[:alnum:]_.-])\.env([.][A-Za-z0-9_-]+)*'; then
  echo "BLOCKED by block-env-read.sh: reading .env files is not allowed." >&2
  echo "  command: $cmd" >&2
  echo "  Those files hold the API URL and any session secrets." >&2
  echo "  Read .env.example instead, or ask the user for the value you need." >&2
  exit 2
fi

exit 0
