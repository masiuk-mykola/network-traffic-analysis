#!/usr/bin/env bash
#
# PostToolUse hook (matcher: Edit|Write|MultiEdit).
# After a change to SOURCE code (not tests / docs / generated), quickly runs the
# unit tests RELATED to that file. Deliberately NON-BLOCKING: always exit 0.
# On failure it only prints the tail of the log to stderr, so intermediate edits
# do not interrupt the flow.

set -uo pipefail

input=$(cat)

if command -v jq >/dev/null 2>&1; then
  file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
else
  file=$(printf '%s' "$input" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
fi

[ -z "$file" ] && exit 0

# Only react to app source under src/. Skip tests, docs, config, generated code.
case "$file" in
  *.test.ts|*.test.tsx|*.spec.ts|*.spec.tsx) exit 0 ;;   # editing a test itself
  */src/lib/api/schema.d.ts) exit 0 ;;                    # generated from openapi.json
  *.md|*.mdx|*.json|*.txt|*.yaml|*.yml) exit 0 ;;
  */src/*.ts|*/src/*.tsx|src/*.ts|src/*.tsx) : ;;        # source file -> proceed
  *) exit 0 ;;
esac

# Need a unit runner; skip silently if vitest is not installed.
npx --no-install vitest --version >/dev/null 2>&1 || exit 0

log=$(mktemp 2>/dev/null || echo "/tmp/post-edit-test.$$")
if ! npx --no-install vitest related "$file" --run --passWithNoTests >"$log" 2>&1; then
  echo "⚠ post-edit-test: related unit tests FAILED for ${file} (non-blocking signal)" >&2
  tail -n 20 "$log" >&2
fi
rm -f "$log"

exit 0
