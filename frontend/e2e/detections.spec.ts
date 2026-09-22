import { expect, test } from '@playwright/test'

import { signIn } from './search-flow'

/**
 * The feed is pushed, not fetched, so these specs watch rather than click. No search is started, so
 * no slot is taken — but a feed outlives the page that opened it by design (it is held for a grace
 * period so a hidden tab does not cost a reconnect), and a spec that walked away would hand the
 * next one a connection still reconnecting in the background. Signing out ends it, which is the
 * same rule the suite already follows for chaos: leave the server as you found it.
 */
test.afterEach(async ({ page }) => {
  await page.request.post('/api/auth/logout').catch(() => undefined)
})

test('the feed opens, says it is live, and lists what the server already holds', async ({
  page,
}) => {
  await signIn(page)
  // The search screen mirrors its settled query back into the address; clicking before that
  // replace lands races it, and the replace wins.
  await expect(page).toHaveURL(/from=/, { timeout: 15_000 })
  await page.getByRole('link', { name: 'Detections' }).click()

  await expect(page).toHaveURL(/\/detections/)
  await expect(page.getByRole('heading', { name: 'Detections' })).toBeVisible()

  const feed = page.getByRole('region', { name: 'Detections' })
  await expect(feed).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })

  // AC-2: what the server still holds is there on opening, not an empty list waiting for an event.
  await expect(feed.getByRole('listitem').first()).toBeVisible({ timeout: 15_000 })
})

test('a detection leads to the session it names', async ({ page }) => {
  await signIn(page)
  await page.goto('/detections')

  const first = page.getByRole('region', { name: 'Detections' }).getByRole('link').first()
  await expect(first).toBeVisible({ timeout: 15_000 })
  const target = await first.getAttribute('href')
  await first.click()

  // The id is a uint64 string: the address must be the one the row carried, digit for digit.
  await expect(page).toHaveURL(new RegExp(`${target}$`))
  const summary = page.getByRole('region', { name: 'Session summary' })
  await expect(summary).toBeVisible({ timeout: 15_000 })
  await expect(summary).toContainText(target!.replace('/sessions/', ''))
})

test('no API token reaches the browser while the feed runs', async ({ page }) => {
  const authorized: string[] = []
  page.on('request', (request) => {
    if (request.headers().authorization) authorized.push(request.url())
  })

  await signIn(page)
  await page.goto('/detections')
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })
  await page.waitForTimeout(2_000)

  expect(authorized).toEqual([])
})

test('a second tab reads the same feed without opening a second connection', async ({
  browser,
}) => {
  // The API grades stream opens per token family, and two tabs are one family. Both tabs therefore
  // share the one connection the server holds; the report is what proves it, this proves both read.
  const context = await browser.newContext()
  const first = await context.newPage()
  try {
    await signIn(first)
    await first.goto('/detections')
    await expect(first.getByText('Live', { exact: true })).toBeVisible({ timeout: 15_000 })

    const second = await context.newPage()
    await second.goto('/detections')

    await expect(second.getByRole('region', { name: 'Detections' })).toBeVisible({
      timeout: 15_000,
    })
    // Whether it says live or reconnecting is the connection's business and it may legitimately be
    // between two of them; what this proves is that the second tab reads the same feed. That there
    // is only one connection behind them is proved by `sse.double_open` in the server's report.
    await expect(second.getByText(/^(Live|Reconnecting)$/)).toBeVisible({ timeout: 15_000 })
  } finally {
    await first.request.post('/api/auth/logout').catch(() => undefined)
    await context.close()
  }
})

test('the feed reports a refused read in place, with a retry', async ({ page }) => {
  await signIn(page)
  // One read refused deterministically: chaos cannot target a path, and refusing everything would
  // take the guard down with it.
  await page.route('**/api/capture/detections*', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ code: 'unavailable', detail: 'busy' }),
    }),
  )

  await page.goto('/detections')

  await expect(page.getByRole('alert')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('heading', { name: 'Detections' })).toBeVisible()
})
