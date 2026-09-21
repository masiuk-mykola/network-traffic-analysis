# Plan 004 — The sign-in form

Spec: `specs/004-login-form.md`. Its open questions were answered: a successful sign-in always lands on
the search screen, the two demo accounts are shown on the page under a note that this is a demo
environment, and someone who already has a session is sent onward instead of seeing the form.

## Files to touch

| Path                                      | Change                                                                                                                           |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `src/lib/auth/credentials.ts` (new)       | The zod schema for the form: email and password, with the limits the API declares. `z.infer` gives the form its type.            |
| `src/lib/auth/credentials.test.ts` (new)  | Empty fields, a non-email, the length limits, and a valid pair.                                                                  |
| `src/app/login/page.tsx`                  | Server component: sends an existing session straight to the search screen, otherwise renders the form and the demo-account note. |
| `src/app/login/login-form.tsx` (new)      | `'use client'`: the form itself, on React Hook Form with the zod resolver, submitting through a mutation.                        |
| `src/app/login/login-form.test.tsx` (new) | Local validation, the pending state, and each failure shape.                                                                     |
| `src/lib/auth/use-sign-in.ts` (new)       | The mutation: posts the credentials to our own route handler, turns a refusal into the shared failure type, then navigates.      |
| `src/components/form/field.tsx` (new)     | Label, control, error and description wired together with matching ids — the pattern every later form reuses.                    |
| `e2e/sign-in.spec.ts` (new)               | The real flow against the running API, including the token-leak check.                                                           |
| `src/app/api/auth/me/route.ts` (new)      | Answers whether a session is live; the page uses it, and item 1.2 will reuse it for the guard.                                   |
| `CLAUDE.md`                               | One line: forms are React Hook Form + zod through the shared field.                                                              |

## Steps

1. **`credentials.ts`** (test first) — `email` is required, trimmed, must look like an email and fit the
   API's 3–254 characters; `password` is required and at most 256. The messages are written for a
   person, not a validator. Nothing here talks to the network.
2. **`field.tsx`** — a small wrapper that renders a label bound to its control, an optional description,
   and an error slot that sets `aria-invalid` and `aria-describedby` on the control. No Radix needed for
   a plain input; this exists so later forms do not each invent their own labelling.
3. **`use-sign-in.ts`** — a `useMutation` that POSTs to our sign-in route handler with the validated
   values, and on success navigates to the search screen with `router.replace` so the form is not left
   in the history. On failure it throws the shared browser failure type, so the form renders it with the
   same words as everything else. `retry: false` — the mutation defaults already forbid retries, and a
   rejected password must never be sent twice.
4. **`login-form.tsx`** — React Hook Form with `zodResolver`, `mode: 'onSubmit'` so the first attempt is
   not pre-judged, `reValidateMode: 'onBlur'`. The submit button is disabled while the mutation is
   pending and shows that it is working. A failure is rendered by the shared error state, which already
   knows to count down a stated wait rather than invite an immediate retry.
5. **`page.tsx`** — on the server, read the session cookie and confirm it resolves to a live session;
   if it does, `redirect` to the search screen. Otherwise render the heading, the form, and a muted
   block naming the two demo accounts with a line saying this is a demo environment.
6. **`me/route.ts`** — a small handler returning the current profile, used by the page to tell a live
   session from a stale cookie. It reuses the existing authorized call path, so a dead session answers
   401 rather than pretending to be signed in.
7. **Tests** — unit for the schema and the form; e2e for the real flow.
8. **`CLAUDE.md`** line.

## Risks

- **Spending the rate-limit budget.** The endpoint refuses further attempts after five failures for one
  email within a minute. Local validation must block empty and malformed submissions so they never
  reach it, and the submit button must be disabled while a request is in flight — otherwise a double
  click costs two of the five.
- **The stated wait is a moment, not a number of seconds.** That is already handled where failures are
  described, and the e2e spec deliberately exercises it by failing five times in a row; if the parsing
  regressed, the form would offer an immediate retry that the server refuses.
- **A password in the wrong place.** The value must never end up in a query string, in a log, or in the
  mutation key. The form posts it in a body and keeps it in component state only.
- **Leaking the API token.** The route handler already returns only the profile, but the e2e spec
  asserts it from the browser's side: after signing in, no storage entry and no response body the page
  can read contains a bearer token.
- **A stale cookie.** A session id whose server-side entry is gone must not let the page redirect a
  visitor into the app, where every call would then fail. The page checks the session resolves, not just
  that a cookie exists.
- **Navigation racing the cookie.** The cookie is set by the route handler in its response; navigating
  before that response is applied would land on a screen that still looks signed out. Navigation happens
  in the mutation's success path, after the response.
- **Chaos.** Under `--chaos storm` the sign-in call can answer 503; the form must show a retryable
  failure rather than a credential error. Under `expiring-tokens` nothing changes for this screen.

## Verification

| #   | Acceptance criterion                                    | How it is proven                                                                                                                                                                              |
| --- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Empty fields are caught locally, nothing is sent        | Unit: the schema rejects both; form test asserts the message appears and the network stub was not called.                                                                                     |
| 2   | A non-email is caught locally                           | Unit: schema rejects `not-an-email`; form test asserts no request.                                                                                                                            |
| 3   | No double submit while in flight                        | Form test: the button is disabled while the mutation is pending, and a second click sends nothing.                                                                                            |
| 4   | A wrong password reads as a rejected pair               | Form test with a 401 stub: the message does not name the email as known or unknown. E2E: wrong password on the real API.                                                                      |
| 5   | A refusal states the wait and blocks an immediate retry | E2E: six wrong attempts in a row; the sixth shows the wait and the retry control is not offered.                                                                                              |
| 6   | Success lands on the search screen                      | E2E: sign in with the analyst account and assert the URL and the heading.                                                                                                                     |
| 7   | No API token reaches the browser                        | E2E: after signing in, assert `localStorage`, `sessionStorage` and the visible cookie carry no bearer token, and that the sign-in response body holds only a profile.                         |
| 8   | The form works from the keyboard alone                  | E2E: tab to each field, type, submit with Enter, and land signed in.                                                                                                                          |
| —   | Nothing else regressed                                  | `npm run format:check`, `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`, `npm run test:e2e`, and `capture-api report` with no FAIL — this item does move the data layer. |
