import { expect, test } from '@playwright/test'

import { dropSearch, signIn, startSearch, watchSearches } from './search-flow'

// Getting to a session means running a search, which holds one of three slots.
test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page }) => {
  watchSearches(page)
})

test.afterEach(async ({ page }) => {
  await dropSearch(page)
})

test('a row opens the session it names, and the session says what it is', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })

  const row = page.getByRole('row').nth(1)
  const href = await row.getAttribute('href')
  await row.click()

  // The id is a uint64 string: the address must be the one the row carried, digit for digit.
  await expect(page).toHaveURL(new RegExp(`${href}$`))
  const summary = page.getByRole('region', { name: 'Session summary' })
  await expect(summary).toBeVisible({ timeout: 15_000 })
  await expect(summary).toContainText(href!.replace('/sessions/', ''))
  await expect(summary).toContainText('hq-core')
})

test('the transaction is labelled the way the server describes it', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })

  // A DNS session is the one whose description is richest, so look for one in the loaded rows.
  const dnsRow = page.getByRole('row').filter({ hasText: 'dns' }).first()
  await expect(dnsRow).toBeVisible({ timeout: 20_000 })
  await dnsRow.click()

  const transaction = page.getByRole('region', { name: 'Transaction' })
  await expect(transaction).toBeVisible({ timeout: 15_000 })
  await expect(transaction).toContainText('Query name')
})

test('a DNS session reads as an exchange, and asks for nothing extra', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })

  const dnsRow = page.getByRole('row').filter({ hasText: 'dns' }).first()
  await expect(dnsRow).toBeVisible({ timeout: 20_000 })

  const asked: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/capture/')) asked.push(new URL(request.url()).pathname)
  })
  await dnsRow.click()

  const exchange = page.getByRole('region', { name: 'DNS exchange' })
  await expect(exchange).toBeVisible({ timeout: 15_000 })
  await expect(exchange).toContainText('Question')
  await expect(exchange).toContainText('Response')
  await expect(page.getByRole('button', { name: 'Copy name' })).toBeVisible()
  // The generic view stays, so nothing decoded is hidden by the layout. (Whether anything is left
  // undescribed depends on the session; the generic list itself is always there.)
  await expect(page.getByRole('region', { name: 'Transaction' })).toBeVisible({ timeout: 15_000 })

  // The exchange is read out of the session the screen already has: the browser asks only for the
  // description of the protocol and for the traffic over time.
  await page.waitForTimeout(2_000)
  // The session itself is never re-read in the browser: the page handed it over. Its traffic and
  // its neighbours are the only session-scoped reads the screen makes.
  const sessionReads = asked.filter((path) => path.includes('/sessions/'))
  expect(sessionReads.filter((path) => !/\/(flow|related)$/.test(path))).toEqual([])
})

test('the traffic of a session is on a timeline, at widths the server accepts', async ({
  page,
}) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })

  const widths: string[] = []
  const refused: number[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.includes('/flow')) widths.push(url.searchParams.get('bucket_ms') ?? '')
  })
  page.on('response', (response) => {
    if (response.url().includes('/flow') && response.status() >= 400)
      refused.push(response.status())
  })

  await page.getByRole('row').nth(1).click()

  const timeline = page.getByRole('region', { name: 'Traffic over time' })
  await expect(timeline).toBeVisible({ timeout: 15_000 })
  await expect(
    timeline.getByText(/in buckets of|no shape to plot|No traffic was recorded/),
  ).toBeVisible({ timeout: 15_000 })

  // Switching what is measured is free; only a different width is read again.
  const asked = widths.length
  await timeline.getByRole('button', { name: 'packets' }).click()
  await page.waitForTimeout(1_000)
  expect(widths).toHaveLength(asked)

  for (const width of widths) {
    expect(Number(width)).toBeGreaterThanOrEqual(100)
    expect(Number(width)).toBeLessThanOrEqual(60_000)
  }
  expect(refused).toEqual([])
})

test('a session lists what is around it, at windows the server accepts', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })

  const windows: string[] = []
  const refused: number[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.includes('/related')) windows.push(url.searchParams.get('window') ?? '')
  })
  page.on('response', (response) => {
    if (response.url().includes('/related') && response.status() >= 400) {
      refused.push(response.status())
    }
  })

  await page.getByRole('row').nth(1).click()

  const related = page.getByRole('region', { name: 'Related sessions' })
  await expect(related).toBeVisible({ timeout: 15_000 })
  await expect(
    related.getByRole('link').first().or(related.getByText('Nothing else in this window')),
  ).toBeVisible({ timeout: 15_000 })

  await related.getByRole('button', { name: '6 hours' }).click()
  await page.waitForTimeout(1_000)

  for (const window of windows) expect(['15m', '1h', '6h']).toContain(window)
  expect(refused).toEqual([])

  // An entry leads to exactly the session it names — the id is a uint64 string, never a number.
  const first = related.getByRole('link').first()
  if (await first.isVisible()) {
    const href = await first.getAttribute('href')
    await first.click()
    await expect(page).toHaveURL(new RegExp(`${href}$`))
    await expect(page.getByRole('region', { name: 'Session summary' })).toBeVisible({
      timeout: 15_000,
    })
  }
})

test('an address naming no session says so, and asks the server once', async ({ page }) => {
  await signIn(page)

  const reads: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/capture/sessions/')) reads.push(request.url())
  })

  await page.goto('/sessions/1')

  await expect(page.getByText('No such session')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('region', { name: 'Session summary' })).toHaveCount(0)
  await page.waitForTimeout(2_000)
  expect(reads).toEqual([])
})
