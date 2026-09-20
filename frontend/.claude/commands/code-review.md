# Code Review

Comprehensive security and quality review of uncommitted changes.

1. Get changed files: `git diff --name-only HEAD` (if empty, `git status --porcelain`).

2. For each changed file, check for:

**Token safety (CRITICAL):**

- An access or refresh token reachable from the browser: in a client component, in a response body, in
  a non-`httpOnly` cookie, in `localStorage`, or in a log
- A module handling tokens without `import 'server-only'`
- `Authorization` on a browser-originated request (scored as `auth.bearer_from_browser`)
- Hardcoded credentials; `CAPTURE_API_URL` exposed as `NEXT_PUBLIC_*`
- XSS: `dangerouslySetInnerHTML`, untrusted API data rendered as HTML
- Missing input validation on route handler payloads

**HTTP discipline (CRITICAL–HIGH, see SETUP.md 5a):**

- More than one refresh in flight per family; a refresh token used twice
- Authorized requests after logout; queries not cancelled, streams not closed, cache not cleared
- Duplicate GETs: raw `fetch` past React Query, or inconsistent `queryKey`s
- Retrying 4xx; ignoring `Retry-After` (HTTP-date on login, seconds elsewhere)
- Cursors not passed verbatim; `limit` above 500; health polled more often than every 10 s
- A search created without `Idempotency-Key`, or a superseded one left undeleted

**Code quality (HIGH):**

- Functions > 50 lines, nesting depth > 4
- Missing error handling; swallowed errors
- Leftover `console.log`, dead code, commented-out blocks
- Comments that restate the code, or any comment not in English
- Missing loading / empty / error states on a fetching surface

**Best practices (MEDIUM):**

- Mutation patterns (use immutable updates)
- Hand-written API types instead of the generated schema; session ids parsed as numbers
- `'use client'` higher in the tree than necessary
- Missing tests for new deterministic logic
- Accessibility issues (a11y): keyboard paths, labels, focus handling

3. Generate a report with: severity (CRITICAL, HIGH, MEDIUM, LOW), file and line, the issue, and a
   suggested fix.

4. Do not hand back a clean verdict with CRITICAL or HIGH issues open — the human commits, so the
   report is the gate.

Never approve code with security vulnerabilities.
