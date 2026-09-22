import { expect, test } from '@playwright/test'

import { calmDown, setChaos, signIn } from './search-flow'

/**
 * The feed across the server ending the stream — deliberately not a spec.
 *
 * Under `storm` the server rotates the stream every twenty seconds, so a minute of watching is
 * three endings, which is the only way `sse.resume` has anything to grade at all: it needs a family
 * that re-opened. That takes minutes and a chaos profile, and a spec that holds the storm for that
 * long hands the next one a server it did not expect — the suite is deliberately deterministic
 * about failure, so this lives beside it rather than in it.
 *
 *   cd ../backend && PYTHONPATH=src .venv/bin/python -m capture_api admin reset
 *   cd frontend && npm run gate:detection-resume
 *   cd ../backend && PYTHONPATH=src .venv/bin/python -m capture_api report --all
 *
 * The verdict is the server's: `sse.double_open`, `sse.resume` and `sse.reconnect_backoff`.
 */
const WATCH_MS = Number(process.env.GATE_WATCH_MS ?? 75_000)

/**
 * `storm` rotates the stream every twenty seconds, which is what `sse.resume` needs. With
 * `expiring-tokens` the access token dies after fifteen, so the stream ends with `reauth` instead —
 * the other ending, and the one that proves the feed comes back under fresh credentials.
 */
const PROFILE = (process.env.GATE_PROFILE ?? 'storm') as 'storm' | 'expiring-tokens'

test('holds the feed open across the server ending it, for the report to grade', async ({
  page,
}) => {
  test.setTimeout(WATCH_MS + 90_000)

  await signIn(page)

  // The profile has to be on *before* the stream opens: the server reads its rotation interval when
  // it builds the stream (300 s calm, 20 s storm), so a storm started afterwards leaves the open
  // stream on calm's interval and it never rotates — which is the one thing this gate exists to
  // exercise.
  await setChaos(page, PROFILE)

  // Navigating under a storm can have the guard's own identity read refused, which hands the whole
  // page to the error boundary. That is this app's behaviour on every screen and nothing to do with
  // the feed, so the navigation is simply attempted again.
  for (let attempt = 0; attempt < 6; attempt += 1) {
    await page.goto('/detections')
    const feed = page.getByRole('region', { name: 'Detections' })
    if (await feed.isVisible({ timeout: 20_000 }).catch(() => false)) break
  }
  await expect(page.getByRole('region', { name: 'Detections' })).toBeVisible({ timeout: 30_000 })

  await page.waitForTimeout(WATCH_MS)

  // Still watching, and still saying so: a feed that had given up would read as stopped.
  await expect(page.getByText(/Live|Reconnecting/).first()).toBeVisible({ timeout: 30_000 })

  await calmDown(page)
  // The feed is held for a grace period after its last reader leaves, so it is ended explicitly
  // rather than left reconnecting behind whatever runs next.
  await page.request.post('/api/auth/logout').catch(() => undefined)
})
