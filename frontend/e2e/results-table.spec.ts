import { expect, test, type Page } from '@playwright/test'

import { dropSearch, signIn, startSearch, watchSearches } from './search-flow'

// Searches hold slots; run one at a time and hand them back.
test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page }) => {
  watchSearches(page)
})

test.afterEach(async ({ page }) => {
  await dropSearch(page)
})

async function runSearch(page: Page) {
  await signIn(page)
  await startSearch(page)
}

test('rows arrive from a real search, with the columns the server publishes', async ({ page }) => {
  await runSearch(page)

  const table = page.getByRole('grid')
  await expect(table).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('columnheader', { name: 'Start' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Summary' })).toBeVisible()
  // The server publishes this one as hidden by default, and there is no column chooser yet.
  await expect(page.getByRole('columnheader', { name: 'Destination country' })).toHaveCount(0)

  await expect(page.getByRole('row').nth(1)).toBeVisible()
})

test('nothing is asked for before a search exists', async ({ page }) => {
  const asked: string[] = []
  await signIn(page)

  page.on('request', (request) => {
    if (request.url().includes('/results')) asked.push(request.url())
  })
  await page.waitForTimeout(2_000)

  expect(asked).toEqual([])
})

test('a row leads to its session', async ({ page }) => {
  await runSearch(page)
  await expect(page.getByRole('grid')).toBeVisible({ timeout: 20_000 })

  const firstRow = page.getByRole('row').nth(1)
  const href = await firstRow.getAttribute('href')
  expect(href).toMatch(/^\/sessions\/\d+$/)

  await firstRow.click()

  await expect(page).toHaveURL(new RegExp(`${href}$`))
})

test('the pages it asks for stay inside the server limit', async ({ page }) => {
  const limits: string[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (url.pathname.includes('/results')) limits.push(url.searchParams.get('limit') ?? '')
  })

  await runSearch(page)
  await expect(page.getByRole('grid')).toBeVisible({ timeout: 20_000 })

  expect(limits.length).toBeGreaterThan(0)
  for (const limit of limits) expect(Number(limit)).toBeLessThanOrEqual(500)
})
