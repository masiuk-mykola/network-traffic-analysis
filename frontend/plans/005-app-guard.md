# Plan 005 — Guarding the app

Spec: `specs/005-app-guard.md`. Its open questions were answered: an API that cannot be reached shows a
failure rather than signing the person out, the shell shows the name and the role only, and signing out
is confirmed in a dialog.

## Files to touch

| Path                                            | Change                                                                                                                                     |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `src/lib/auth/session.ts` (new)                 | `requireProfile()`: returns the signed-in profile, redirects to sign-in when there is no session, rethrows when the API is unreachable.    |
| `src/lib/auth/redirect-target.ts` (new)         | `safeRedirectTarget(value)`: accepts only a same-site path, so the destination cannot point elsewhere.                                     |
| `src/lib/auth/redirect-target.test.ts` (new)    | Absolute URLs, protocol-relative `//evil.example`, backslashes, encoded forms, and the empty case.                                         |
| `src/app/(app)/layout.tsx` (new)                | The signed-in shell: calls `requireProfile()` once per navigation, renders the header with the name, the role and sign-out, then the page. |
| `src/app/(app)/search/page.tsx` (moved)         | Existing placeholder moved under the guarded group; content unchanged.                                                                     |
| `src/app/(app)/sessions/[id]/page.tsx` (moved)  | Same.                                                                                                                                      |
| `src/app/(app)/error.tsx` (new)                 | Renders the shared error state when the guard itself fails, with a retry — the session is not thrown away.                                 |
| `src/components/app-header.tsx` (new)           | Name, role badge, sign-out trigger. Server component; the trigger is a small client leaf.                                                  |
| `src/components/sign-out-button.tsx` (new)      | `'use client'`: Radix dialog confirming, then posts to the sign-out handler, clears the query cache and navigates.                         |
| `src/components/sign-out-button.test.tsx` (new) | Confirming posts and clears; dismissing does neither.                                                                                      |
| `src/app/login/page.tsx`                        | Reads the destination from the query string through `safeRedirectTarget` and hands it to the form.                                         |
| `src/app/login/login-form.tsx`                  | Accepts the destination and passes it to the mutation.                                                                                     |
| `src/lib/auth/use-sign-in.ts`                   | Navigates to the given destination, defaulting to the search screen.                                                                       |
| `e2e/guard.spec.ts` (new)                       | Anonymous access, a dead cookie, return-to-destination, an external destination, sign-out and history.                                     |
| `CLAUDE.md`                                     | One line: protected screens live under the guarded group; the guard is the layout, not a check per page.                                   |

## Steps

1. **`redirect-target.ts`** (test first) — accept a value only when it starts with a single `/`, is not
   `//` or `/\`, and contains no scheme after decoding; otherwise return the search path. This runs
   before anything is redirected anywhere.
2. **`session.ts`** — `requireProfile()` reads the session id first (outside any try, so the dynamic
   marker is not swallowed — the same trap as on the sign-in page), then calls the profile endpoint.
   No session or a 401 → `redirect('/login?next=…')`. Anything else — a 503, a timeout, a contract
   failure — is rethrown so the error boundary shows it.
3. **Route group** — create `src/app/(app)/` and move the two placeholder screens into it unchanged.
   The group adds no URL segment, so `/search` and `/sessions/{id}` keep their addresses.
4. **`(app)/layout.tsx`** — `await requireProfile()` once, render `AppHeader` with it, then `children`.
   One identity call per navigation, and the pages below it need none.
5. **`(app)/error.tsx`** — a client error boundary rendering the shared error state with a retry that
   calls `reset()`. This is what makes a struggling API an error instead of a sign-out.
6. **`AppHeader`** — name, a small role badge, and the sign-out trigger, in a bar that is the same on
   every guarded screen.
7. **`SignOutButton`** — Radix dialog to confirm; on confirm, POST to the sign-out handler, then
   `queryClient.clear()` and `router.replace('/login')` followed by `router.refresh()`. Clearing the
   cache before navigating is what stops a later render from using data fetched under the old session.
8. **Destination through sign-in** — the login page reads `next`, sanitizes it, passes it to the form,
   which hands it to the mutation; the mutation replaces to it.
9. **Tests** — unit for the sanitizer and the sign-out dialog; e2e for the whole flow.
10. **`CLAUDE.md`** line.

## Risks

- **An open redirect.** `next` is attacker-controlled: `//evil.example`, `/\evil.example`,
  `https://evil.example` and their encoded forms all have to collapse to the search path. The sanitizer
  is the only place that decides, and it is tested against each of those shapes.
- **Signing out on a hiccup.** Treating every failed identity check as "not signed in" would throw a
  working session away on a single 503 under `--chaos storm`. Only a 401 or a missing session redirects;
  everything else reaches the error boundary.
- **Requests after sign-out.** The backend scores any authorized call later than five seconds after
  revocation (`auth.logout_once`). The cache must be cleared and in-flight queries cancelled before the
  navigation, or a component that unmounts mid-flight can still land a request.
- **An identity call per page.** Putting `requireProfile()` in each page instead of the layout would
  multiply calls per navigation and start tripping `http.get_dedupe`. It belongs in the layout exactly
  once.
- **Swallowing Next's dynamic signal.** Reading cookies inside a `try/catch` makes the route render as
  if nobody were signed in — this already bit the sign-in page. The cookie read stays outside.
- **Back after sign-out.** A cached RSC payload can render a guarded screen from history. `replace` plus
  `router.refresh()` after clearing the cache is the mitigation, and the e2e spec checks it by pressing
  back.
- **The observer account.** It is read-only with less data; the header must render its role without
  assuming permissions the account does not have.

## Verification

| #   | Acceptance criterion                         | How it is proven                                                                                                                                         |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | No session → sign in                         | E2E: open `/search` with no cookie and land on `/login`. Also `curl` the route and see a redirect, not a 200.                                            |
| 2   | A dead cookie counts as no session           | E2E: sign in, revoke the session from the backend's admin command, open a guarded screen, land on sign in.                                               |
| 3   | Return to the original destination           | E2E: open `/sessions/123` anonymously, sign in, end up on `/sessions/123`.                                                                               |
| 4   | An external destination is ignored           | Unit: each hostile shape collapses to `/search`. E2E: `/login?next=https://example.com` signs in to `/search`.                                           |
| 5   | Name and role are visible                    | E2E: after signing in as the analyst, the header shows the display name and the role.                                                                    |
| 6   | Sign-out returns to sign in, back stays out  | E2E: confirm the dialog, land on `/login`, press back, still not on a guarded screen.                                                                    |
| 7   | No request on the old session after sign-out | E2E: record requests after sign-out for five seconds and assert none goes to the proxy. Then `capture-api report` with `auth.logout_once` not FAIL.      |
| 8   | An unreachable API shows a failure           | E2E: stop the API container, open a guarded screen with a valid session, see the error state and not the sign-in form.                                   |
| —   | Nothing else regressed                       | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL. |
