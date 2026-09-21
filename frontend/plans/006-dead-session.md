# Plan 006 — When the session dies mid-use

Spec: `specs/006-dead-session.md`. Its open questions were answered: a job that outlives the session is
not resumed (returning to the same screen is enough until the search exists), the reason is shown as a
toast, and a death discovered by a background request is acted on immediately, exactly like one
discovered by a click.

## Files to touch

| Path                                        | Change                                                                                                                             |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/auth/session-expiry.ts` (new)      | `createExpiryHandler({ onExpired })`: recognises the failure, fires once, and stays quiet for everything else.                     |
| `src/lib/auth/session-expiry.test.ts` (new) | One reaction for many simultaneous failures; other failures and non-HTTP errors ignored; re-armed after a new sign-in.             |
| `src/app/providers.tsx`                     | Toast provider moves outside the query client; the client is built with a cache-level failure handler that runs the reaction once. |
| `src/app/providers.test.tsx` (new)          | A failing query with the dead-session code cancels, clears and navigates; a 503 does none of it.                                   |
| `e2e/session-expiry.spec.ts` (new)          | Revoke the session from the backend mid-use, then watch what the browser does for the next few seconds.                            |
| `CLAUDE.md`                                 | One line: a dead session is handled in one place, not per screen.                                                                  |

## Steps

1. **`session-expiry.ts`** (test first) — a factory holding a single `handled` flag. `handleFailure`
   returns early unless the error is ours and carries the dead-session code; the first one calls
   `onExpired()`, the rest are ignored. `rearm()` clears the flag and is called when a sign-in
   succeeds, so the next session gets its own reaction.
2. **Provider order** — `ToastProvider` moves to wrap `QueryClientProvider`, because the reaction needs
   to say something and the handler is built where the query client is. The devtools stay inside.
3. **The reaction** — in `Providers`, build the client with `queryCache` and `mutationCache` whose
   `onError` both feed the handler. `onExpired` does, in this order: `cancelQueries()` so nothing in
   flight can land after the session is gone, `clear()` so no screen can render the old account's data,
   a toast explaining what happened, then `router.replace('/login?next=<current path>')`. The order is
   the point — navigating first would leave queries running during the transition.
4. **Where we came from** — the current path is read at the moment of the failure and sanitized through
   the existing redirect guard, so the same rules apply as when the guard sends someone to sign in.
5. **Not on the sign-in screen** — the handler is a no-op when the app is already there, so a stray
   failure cannot bounce a person who is trying to sign in.
6. **Tests** — unit for the factory, a provider-level test driving a real failing query, and an e2e
   that revokes the session for real.
7. **`CLAUDE.md`** line.

## Risks

- **A reaction storm.** Several queries fail in the same tick; without the flag each would cancel,
  clear and navigate, producing repeated navigations and repeated toasts. The flag is the fix and the
  first unit test.
- **The five-second window.** The API counts any authorised call later than five seconds after
  revocation (`auth.logout_once`). Cancelling before navigating is what keeps us inside it; a component
  that unmounts mid-flight during the navigation would otherwise still land its request.
- **Colliding with sign-out.** Signing out revokes the session deliberately; queries failing right
  afterwards must not trigger a second navigation on top of the one sign-out already does. Sign-out
  clears the cache before its own navigation, and the handler is inert once the app is on sign-in.
- **`expiring-tokens` chaos.** Access tokens die every fifteen seconds there and are renewed on the
  server without the browser noticing. Only the dead-session code may trigger this reaction — a plain
  401 that the refresh path handles must never reach it.
- **A toast that nobody sees.** The explanation is a toast, which lives in the client app: it survives
  the client-side navigation to sign in, but not a full page reload. Accepted, with the sanitized
  destination as the thing that actually matters.
- **Cache left behind.** Clearing is not optional: the other demo account sees less data, and a stale
  entry rendered after switching accounts would look like a permission bug rather than a cache bug.

## Verification

| #   | Acceptance criterion                                | How it is proven                                                                                                                                         |
| --- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | A dead session takes the person to sign in          | Provider test: a query failing with the code navigates to `/login`. E2E: revoke mid-use, land on sign in.                                                |
| 2   | Nothing authorised after five seconds               | E2E: record proxy requests for six seconds after the revocation and assert none. Then `capture-api report` — `auth.logout_once` not FAIL.                |
| 3   | Many failures, one return                           | Unit: ten failures, one `onExpired`. Provider test: two failing queries, one navigation.                                                                 |
| 4   | The sign-in screen explains itself                  | E2E: the toast is visible after landing on sign in.                                                                                                      |
| 5   | Signing in again returns to the interrupted screen  | E2E: revoked on `/sessions/{id}`, sign in again, end up back there.                                                                                      |
| 6   | The other account does not see the first one's data | E2E: sign in as the analyst, revoke, sign in as the observer, and assert the cache was not reused.                                                       |
| 7   | A server error does not sign anyone out             | Unit and provider test: a 503 and a 429 leave the cache and the location alone.                                                                          |
| —   | Nothing else regressed                              | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL. |
