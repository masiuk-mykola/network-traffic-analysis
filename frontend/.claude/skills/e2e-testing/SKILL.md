---
name: e2e-testing
description: Write Playwright e2e tests for THIS app — what the suite may and may not mock, how to sign in through our own route handler, and how to keep specs from tripping the backend's HTTP checks. Use whenever adding or changing anything under e2e/.
---

# e2e testing — Playwright in this repo

Specs live in `e2e/`, config in `playwright.config.ts`. `npm run test:e2e` starts its own dev server
(`reuseExistingServer` unless CI), base URL `http://localhost:3000`, chromium only.

## What may be mocked

- **Our own route handlers** (`/api/**`): mock freely with `page.route` when the test is about UI
  behaviour — an error state, an empty state, a slow response.
- **The capture API itself**: never mocked from the browser — the browser cannot reach it anyway. A
  test that needs real data needs the API running (`../backend`, see the `http-discipline` skill).

Prefer a real sign-in through `/api/auth/login` over faking a session: the session store lives in the
server process, so a hand-made cookie will not resolve to anything.

## Writing a spec

- Name the test for the behavior in English: `test('search page shows an empty state', …)`.
- Select by role or visible text (`getByRole`, `getByText`), not by CSS class — Tailwind classes churn.
- Use web-first assertions (`await expect(locator).toBeVisible()`); never `waitForTimeout`.
- One user-visible outcome per test. Keep setup in a fixture or `beforeEach`, not copied per test.
- Tests must be independent and order-free; they run in parallel.

## Things specific to this app

- A search is a server-side job: assert the progress state and the first page of results, not a
  fixed row count — the data is deterministic but the timing is not.
- Do not poll the API from a test loop; drive the UI and let the app's own polling do the work,
  otherwise the suite itself trips `poll.health_interval` or `http.get_dedupe`.
- Session ids are long decimal strings — compare them as strings.
- When a spec needs an expired token or a revoked session, use the backend's `admin expire-tokens` /
  `admin revoke` rather than waiting 90 seconds.

## Before calling it done

`npm run test:e2e` green locally, and the spec fails if you revert the feature it covers. The HTML
report lands in `playwright-report/` (git-ignored).
