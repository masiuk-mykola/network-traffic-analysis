#!/usr/bin/env bash
#
# PostToolUse hook (matcher: Edit|Write|MultiEdit).
# Formats ONLY the file that was just edited, using the formatter for its type.
# Never fails the tool call: missing formatter / unknown type / error -> exit 0.

set -uo pipefail

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
else
  file=$(printf '%s' "$input" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
fi

[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

case "$file" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.css|*.scss|*.md|*.mdx|*.html|*.yaml|*.yml)
    if npx --no-install prettier --version >/dev/null 2>&1; then
      npx --no-install prettier --write --log-level silent "$file" >/dev/null 2>&1 || true
    fi
    ;;
  *.py)
    if command -v black >/dev/null 2>&1; then
      black --quiet "$file" >/dev/null 2>&1 || true
    fi
    ;;
esac

exit 0
