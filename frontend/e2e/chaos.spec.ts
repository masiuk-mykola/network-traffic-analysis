import { expect, test, type Page } from '@playwright/test'

import { calmDown, dropSearch, setChaos, signIn, startSearch, watchSearches } from './search-flow'

// The server is made to misbehave here; nothing else may inherit that.
test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page }) => {
  watchSearches(page)
})

test.afterEach(async ({ page }) => {
  await calmDown(page)
  await dropSearch(page)
})

/** Refuse one read for certain, without touching the rest. Chaos cannot target a path; this can. */
async function refuse(page: Page, path: string) {
  await page.route(`**/api/capture/${path}*`, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'unavailable', detail: 'the index is busy' }),
    }),
  )
}

test('a refused capture-point read costs the list, not the screen', async ({ page }) => {
  await refuse(page, 'sensors')
  await signIn(page)

  const points = page.getByRole('group', { name: 'Capture points' })
  await expect(points.getByRole('alert')).toBeVisible({ timeout: 20_000 })
  // Everything that does not depend on that read is still here.
  await expect(page.getByLabel('From (UTC)')).toBeVisible()
  await expect(page.getByLabel('To (UTC)')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run search' })).toBeDisabled()
})

test('lifting the refusal brings the list back on the next attempt', async ({ page }) => {
  await refuse(page, 'sensors')
  await signIn(page)
  const points = page.getByRole('group', { name: 'Capture points' })
  await expect(points.getByRole('alert')).toBeVisible({ timeout: 20_000 })

  await page.unroute('**/api/capture/sensors*')
  await points.getByRole('button', { name: /try(ing)? again/i }).click()

  await expect(page.getByRole('listitem').filter({ hasText: 'HQ Core' })).toBeVisible({
    timeout: 20_000,
  })
  await expect(points.getByRole('alert')).toHaveCount(0)
})

test('a refused session read keeps the way back', async ({ page }) => {
  await signIn(page)
  await refuse(page, 'sessions')

  await page.goto('/sessions/72057639299711028')

  await expect(page.getByRole('alert')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: /back to results/i })).toBeVisible()
})

test('a refused start is reported by the control, and the query survives it', async ({ page }) => {
  await signIn(page)
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()

  // The server refuses the start once, the way it does when its index is busy.
  let refusals = 0
  await page.route('**/api/searches', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    refusals += 1
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      headers: { 'retry-after': '1' },
      body: JSON.stringify({ code: 'unavailable', detail: 'the index is busy' }),
    })
  })

  await page.getByRole('button', { name: 'Run search' }).click()

  await expect(
    page.getByRole('alert').filter({ hasText: /server is having trouble/i }),
  ).toBeVisible({ timeout: 20_000 })
  expect(refusals).toBe(1)
  // Nothing about the query is lost, and the control comes back.
  await expect(
    page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox'),
  ).toBeChecked()
  await expect(page.getByLabel('From (UTC)')).toBeVisible()
  await expect(page.getByRole('button', { name: /run search|try again in/i })).toBeVisible({
    timeout: 20_000,
  })
})

test('a fifteen-second access token is never the reader’s problem', async ({ page }) => {
  await setChaos(page, 'expiring-tokens')
  await signIn(page)

  // Outlive the token, then use the screen.
  await page.waitForTimeout(18_000)
  await startSearch(page)

  await expect(page.getByRole('grid')).toBeVisible({ timeout: 30_000 })
  await expect(page).toHaveURL(/\/search/)
  // The renewal happens on the server: nothing is explained to the reader, because nothing broke.
  await expect(
    page.getByRole('region', { name: 'Notifications' }).getByText('Your session ended'),
  ).toHaveCount(0)
  await expect(page.getByRole('banner')).toContainText('Ana Duarte')
})
