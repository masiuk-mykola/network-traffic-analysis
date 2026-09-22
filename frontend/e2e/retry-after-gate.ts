import { test, type Page } from '@playwright/test'

import { ANALYST, calmDown, dropSearch, setChaos, watchSearches } from './search-flow'

/**
 * The traffic generator for `http.retry_after_violations` — deliberately not a spec.
 *
 * The suite next door is deterministic about failure: it refuses one read with `page.route` and
 * asserts what the screen does. That is the right shape for a behaviour, and the wrong shape for
 * this check, which is about the gap between two requests and only shows itself over minutes of
 * refused reads. An assertion here would abort the run long before enough traffic accumulated,
 * which is exactly why the third cause resisted isolation for so long.
 *
 * So nothing in this file asserts. Every action is best-effort: under a profile that refuses every
 * read the screen shows its error state rather than its results, and that is a round that
 * generated traffic, not a failure. The verdict comes from the server afterwards:
 *
 *   cd ../backend && PYTHONPATH=src .venv/bin/python -m capture_api admin reset
 *   npm run gate:retry-after
 *   cd ../backend && PYTHONPATH=src .venv/bin/python -m capture_api report --since 600
 *
 * It takes the account's search slots and signs in as the shared fixture account, so it runs alone
 * — never beside `npm run test:e2e`.
 */

/**
 * `forced` refuses every read, which is how the cause was found; `storm` is the profile the check
 * actually failed under; `expiring-tokens` is the regression guard, because a refresh taken inside
 * someone else's window would trade a scored retry for a dead session.
 */
const PROFILE = (process.env.GATE_PROFILE ?? 'forced') as 'forced' | 'storm' | 'expiring-tokens'
const ROUNDS = Number(process.env.GATE_ROUNDS ?? 6)

const SHORT_MS = 8_000

/** Best-effort: a refused read is a round that produced traffic, not a reason to stop. */
async function attempt(what: () => Promise<unknown>): Promise<void> {
  await what().catch(() => undefined)
}

async function signIn(page: Page) {
  await attempt(() => page.goto('/login'))
  await attempt(() => page.getByLabel('Email').fill(ANALYST.email))
  await attempt(() => page.getByLabel('Password').fill(ANALYST.password))
  await attempt(() => page.getByRole('button', { name: 'Sign in' }).click())
  await attempt(() => page.waitForURL(/\/search/, { timeout: SHORT_MS }))
}

/** Every read refused, with a delay named on each, so a window is always open. */
const REFUSE_EVERYTHING = { get_503_rate: 1.0, drop_rate: 0.0 }

/**
 * One round of the flow the check scores: a job started, watched, left and returned to, re-ordered,
 * and handed back — from both sides of the render boundary.
 *
 * The job is started while the server is calm, because a screen whose every read is refused never
 * offers a capture point to tick: with refusals on from the start the generator produces no search
 * traffic at all. The storm goes on once there is something to ask about.
 */
async function round(page: Page, index: number) {
  if (PROFILE === 'forced') await setChaos(page, 'calm')

  await attempt(() => page.goto('/search'))
  await attempt(() =>
    page
      .getByRole('listitem')
      .filter({ hasText: 'HQ Core' })
      .getByRole('checkbox')
      .click({ timeout: SHORT_MS }),
  )
  await attempt(() => page.getByRole('button', { name: 'Run search' }).click({ timeout: SHORT_MS }))
  await attempt(() => page.waitForURL(/search=srch_/, { timeout: SHORT_MS }))

  const job = new URL(page.url()).searchParams.get('search')
  if (PROFILE === 'forced') await setChaos(page, 'calm', REFUSE_EVERYTHING)

  if (!job) {
    console.log(`gate: round ${index} started no job`)
    return
  }

  // Let the browser poll the status for a while: the refusals that open a window arrive here.
  await page.waitForTimeout(2_000)

  // Away and back — a server render of the same job, on the other side of the boundary from the
  // poll that may have just been refused. Both navigations also read the profile behind the guard.
  await attempt(() => page.goto('/sessions/not-a-session'))
  await attempt(() => page.goto(`/search?search=${job}`))
  await page.waitForTimeout(1_500)

  // A changed order is another server render, and another read of the results template.
  await attempt(() => page.goto(`/search?search=${job}&sort=-bytes`))
  await page.waitForTimeout(1_500)

  // The supersede path: a DELETE on the same template as the reads above, from a third caller.
  await attempt(() => page.getByRole('button', { name: 'Stop' }).click({ timeout: 2_000 }))
  await attempt(() => page.request.delete(`/api/searches/${job}`))

  console.log(`gate: round ${index} done (${job})`)
}

test('drives traffic through a refused search, for the report to grade', async ({ page }) => {
  watchSearches(page)

  if (PROFILE !== 'forced') await setChaos(page, PROFILE)

  try {
    // Signing in under a storm mostly fails to sign in, which produces no traffic to grade.
    if (PROFILE === 'forced') await setChaos(page, 'calm')
    await signIn(page)
    for (let index = 1; index <= ROUNDS; index += 1) await round(page, index)
  } finally {
    await attempt(() => dropSearch(page))
    await calmDown(page)
  }
})
