# Plan 002 — The state kit

Spec: `specs/002-state-kit.md`. Its open questions were answered: request-shaped 4xx get no special
presentation yet (they read as a non-retryable failure until the search form can point at a field),
the API's stable code is shown discreetly, icons are in, and minimal toasts are in scope.

## Files to touch

| Path                                            | Change                                                                                                                           |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `package.json`                                  | Add `lucide-react` and `@radix-ui/react-toast`.                                                                                  |
| `src/app/globals.css`                           | Add the few semantic tokens these pieces need (muted text, border, danger) in both colour schemes; keep the existing two tokens. |
| `src/lib/api/failure.ts` (new)                  | `describeFailure(error)` → `{ title, detail, code, retryable, retryAfterMs }`. The one place that decides how a failure reads.   |
| `src/lib/api/failure.test.ts` (new)             | Every branch: retryable, permission, gone session, stated wait, upstream contract, unknown error.                                |
| `src/components/states/loading-state.tsx` (new) | Spinner + label, `role="status"`, `aria-live="polite"`; `variant: 'page' \| 'region'`.                                           |
| `src/components/states/skeleton.tsx` (new)      | Layout-preserving placeholder, `aria-hidden`, used where the shape of the coming content is known.                               |
| `src/components/states/empty-state.tsx` (new)   | Icon + title + optional description + optional action slot. Not an alert.                                                        |
| `src/components/states/error-state.tsx` (new)   | Renders `describeFailure` output: icon, title, detail, discreet code, retry button only when retryable, wait text when stated.   |
| `src/components/states/index.ts` (new)          | Barrel so screens import one path.                                                                                               |
| `src/components/states/*.test.tsx` (new)        | One test file per piece: role, retry wiring, absence of retry, wait text, region vs page.                                        |
| `src/components/toast/toast-provider.tsx` (new) | Radix `Toast.Provider` + viewport, mounted once; `'use client'`.                                                                 |
| `src/components/toast/use-toast.ts` (new)       | `useToast()` → `{ notify }`; two kinds, `error` and `info`; errors take a failure and show its code.                             |
| `src/components/toast/use-toast.test.tsx` (new) | Queueing, dismissal, and that an error toast carries the code.                                                                   |
| `src/app/providers.tsx`                         | Wrap children in the toast provider, inside `QueryClientProvider`.                                                               |
| `e2e/states.spec.ts` (new)                      | Drives a temporary probe route to prove the states render and the retry works in a real browser.                                 |
| `src/app/dev/states/page.tsx` (new)             | A gallery route rendering every state, used by the e2e spec and by eye. Excluded from production builds.                         |
| `CLAUDE.md`                                     | One line: where the state pieces live and that screens must not hand-roll their own.                                             |

## Steps

1. **Install** `lucide-react` and `@radix-ui/react-toast`. Nothing else; the existing Radix primitives
   cover the rest.
2. **Tokens** — add `--color-muted`, `--color-border`, `--color-danger` (and their dark values) to
   `globals.css` next to the two that exist. Everything below styles from these, never from raw hexes.
3. **`describeFailure`** (test first) — maps an `HttpError` to what the user sees:
   - `session_revoked` → "Your session ended", not retryable, tells the user to sign in again;
   - 403 → "You do not have access to this", not retryable;
   - 404 → "Not found", not retryable;
   - 429 → retryable, `retryAfterMs` carried through so the UI can say when;
   - `upstream_contract` (our 502) → "Something went wrong on our side", retryable, no server detail;
   - 5xx and network/unknown → "Could not load this", retryable;
   - other 4xx → not retryable, uses the API's own detail as the body text (this is where the
     request-shaped errors land until the search form can do better).
     It returns the stable code so the UI can print it discreetly, and never returns a code for an
     error that is not an `HttpError`.
4. **`LoadingState`** — `role="status"` with a polite live region and a visible label; `page` variant
   centres in the viewport, `region` fills its container. A CSS-only spinner, no animation library.
5. **`Skeleton`** — a `div` with fixed dimensions from props and a subtle pulse, `aria-hidden` so the
   live region does the announcing, not the placeholder.
6. **`EmptyState`** — icon, title, optional description, optional action node. Deliberately not
   `role="alert"`; it is a normal region, which is what keeps it distinct from a failure semantically.
7. **`ErrorState`** — takes the raw error, runs it through `describeFailure`, renders
   `role="alert"`; shows the retry button only when `retryable` and an `onRetry` was given; when a wait
   is stated, shows "Try again in N s" and disables the button until it elapses; prints the code in
   muted small text.
8. **Toasts** — provider with a single viewport in the corner, swipe-to-dismiss defaults from Radix, a
   `notify({ kind, title, detail, code })` API, and an error helper that takes a failure object. Keep
   the queue in component state; no global store.
9. **Wire the provider** in `src/app/providers.tsx` so every screen can reach `useToast`.
10. **Gallery route** `src/app/dev/states/page.tsx` renders each piece with representative inputs
    (loading, empty, four failure kinds, a toast trigger). Guard it: return `notFound()` when
    `process.env.NODE_ENV === 'production'`, so it never ships.
11. **Tests** — unit per component and for `describeFailure`; one e2e spec that opens the gallery,
    checks the announced roles, clicks retry and sees the handler fire, and checks that the permission
    state has no retry control.
12. **`CLAUDE.md`** — one line under Conventions.

## Risks

- **Retry that fights the server.** A retry button next to a 429 invites exactly the request the server
  just refused. The countdown from `retryAfterMs` is the mitigation; getting it wrong risks
  `http.retry_after_violations`, which is scored. The button must be disabled, not merely labelled.
- **Double retry paths.** React Query already retries on its own policy; the button is a _manual_
  refetch on top of that. If a screen wires the button to something that also triggers the automatic
  path, one click becomes several requests and trips `http.get_dedupe`. The button takes an explicit
  `onRetry` and this item wires none of it to real queries.
- **Announcing on every render.** A live region that re-renders with the same text can re-announce it.
  Keep the loading label stable and mount the region once per state, rather than swapping text inside
  one region.
- **Leaking internals.** `describeFailure` must never put the upstream detail of our own 502 on screen —
  that body is a generic sentence by design, and the test asserts it.
- **The gallery route shipping.** A dev-only route that survives into production is a small but real
  embarrassment; the `notFound()` guard is tested by the e2e spec running against the dev server only.
- **Chaos profiles.** Under `storm` the API answers 503 with a wait; under `expiring-tokens` a session
  can die mid-screen. Both must land in the right branch of `describeFailure`; the tests use the real
  shapes the proxy produces rather than invented ones.
- **Token leakage.** These are client components; none of them may import anything under
  `src/lib/api/` other than the browser-safe `http-error` and `failure` modules.

## Verification

| #   | Acceptance criterion                         | How it is proven                                                                                                                                                                                                              |
| --- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Progress is announced                        | Unit: the loading piece exposes `role="status"` with a polite live region and a non-empty label.                                                                                                                              |
| 2   | Empty is distinct from failure               | Unit: the empty piece has no `role="alert"`; the error piece does; both render their own icon and title.                                                                                                                      |
| 3   | A retryable failure offers a working retry   | Unit: clicking calls `onRetry`. E2E: the gallery's retry button fires its handler in a real browser.                                                                                                                          |
| 4   | Permission and gone session show no retry    | Unit: both branches render no button even when `onRetry` is passed. E2E: the permission card has no button.                                                                                                                   |
| 5   | A stated wait replaces an immediate retry    | Unit: with `retryAfterMs`, the button is disabled and the wait is shown; after fake timers advance, enabled.                                                                                                                  |
| 6   | Our own failure reads generically            | Unit: the upstream-contract branch shows a generic sentence and no schema detail; asserted by absence.                                                                                                                        |
| 7   | Page and region variants both read correctly | Unit: both variants render the same semantics with different layout classes. E2E: both appear in the gallery.                                                                                                                 |
| 8   | Reverting any rule turns a test red          | Revert each branch of `describeFailure` locally before hand-off and confirm a red test.                                                                                                                                       |
| —   | Nothing else regressed                       | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`. The data layer does not move, so `capture-api report` is unchanged — run it once to confirm no new traffic. |
