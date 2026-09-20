#!/usr/bin/env bash
#
# PreToolUse hook (matcher: Bash).
# Reads the tool-call JSON from stdin and blocks obviously destructive shell
# commands plus force-pushes to protected branches.
#   exit 2 = BLOCK (reason on stderr)   exit 0 = allow
#
# Extend the deny-list by adding ERE patterns to DANGEROUS_PATTERNS below.

set -uo pipefail

# --- Deny-list: extended regular expressions (grep -E). Add freely. ----------
DANGEROUS_PATTERNS=(
  'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+(-[a-zA-Z]+[[:space:]]+)*(/|~|\$HOME)([[:space:]]|$)'  # rm -rf / , rm -rf ~
  ':[[:space:]]*\(\)[[:space:]]*\{[[:space:]]*:[[:space:]]*\|[[:space:]]*:'                                 # fork bomb :(){ :|:& };:
  'mkfs(\.[a-z0-9]+)?[[:space:]]'                                                                            # mkfs / mkfs.ext4 ...
  'dd[[:space:]]+.*of=/dev/'                                                                                 # dd of=/dev/sdX
  '>[[:space:]]*/dev/(sd|nvme|disk)'                                                                         # > /dev/sdX
  'chmod[[:space:]]+-[a-zA-Z]*R[a-zA-Z]*[[:space:]]+777[[:space:]]+/'                                        # chmod -R 777 /
  '(curl|wget)[[:space:]].*\|[[:space:]]*(sudo[[:space:]]+)?(sh|bash|zsh)([[:space:]]|$)'                    # curl ... | sh
)

# --- Branches that must never receive a force-push. --------------------------
PROTECTED_BRANCHES=(develop production staging main master)
# -----------------------------------------------------------------------------

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
else
  cmd=$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)".*/\1/p')
fi

[ -z "$cmd" ] && exit 0

# 1) Destructive command patterns.
for pat in "${DANGEROUS_PATTERNS[@]}"; do
  if printf '%s' "$cmd" | grep -Eq "$pat"; then
    echo "BLOCKED by block-dangerous.sh: command matches dangerous pattern:" >&2
    echo "  pattern: $pat" >&2
    echo "  command: $cmd" >&2
    exit 2
  fi
done

# 2) Force-push to a protected branch.
if printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+.*push' &&
   printf '%s' "$cmd" | grep -Eq '(--force-with-lease|--force|[[:space:]]-[a-zA-Z]*f)'; then

  current=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  for br in "${PROTECTED_BRANCHES[@]}"; do
    # explicit branch named in the command, or currently on the protected branch
    if printf '%s' "$cmd" | grep -Eq "(^|[[:space:]:/])$br([[:space:]:]|$)" || [ "$current" = "$br" ]; then
      echo "BLOCKED by block-dangerous.sh: force-push to protected branch '$br' is not allowed." >&2
      echo "  command: $cmd" >&2
      exit 2
    fi
  done
fi

exit 0
