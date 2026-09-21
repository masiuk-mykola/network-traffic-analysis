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

async function runToEnd(page: Page) {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByText('Search finished')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
}

const firstRowText = (page: Page) => page.getByRole('row').nth(1).innerText()

test('a finished search can be re-ordered, and the address says so', async ({ page }) => {
  await runToEnd(page)
  const before = await firstRowText(page)

  await page.getByRole('button', { name: /bytes/i }).click()

  await expect(page).toHaveURL(/sort=-bytes/)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('columnheader', { name: /bytes/i })).toHaveAttribute(
    'aria-sort',
    'descending',
  )
  expect(await firstRowText(page)).not.toBe(before)
})

test('the address restores the same order without starting a second search', async ({ page }) => {
  await runToEnd(page)
  await page.getByRole('button', { name: /bytes/i }).click()
  await expect(page).toHaveURL(/sort=-bytes/)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
  const ordered = await firstRowText(page)
  const shared = page.url()

  const created: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/searches')) {
      created.push(request.url())
    }
  })

  await page.goto(shared)

  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
  expect(await firstRowText(page)).toBe(ordered)
  expect(created).toEqual([])
})

test('a row opens its session, and coming back keeps the order and the rows', async ({ page }) => {
  await runToEnd(page)
  await page.getByRole('button', { name: /risk/i }).click()
  await expect(page).toHaveURL(/sort=-risk/)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
  const ordered = await firstRowText(page)

  await page.getByRole('row').nth(1).click()
  await expect(page).toHaveURL(/\/sessions\/\d+$/)

  const reread: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/results')) reread.push(request.url())
  })

  await page.goBack()

  await expect(page).toHaveURL(/sort=-risk/)
  await expect(page.getByRole('table')).toBeVisible({ timeout: 20_000 })
  expect(await firstRowText(page)).toBe(ordered)
  expect(reread).toEqual([])
})

test('an address naming a search the server does not have explains itself', async ({ page }) => {
  await signIn(page)

  await page.goto('/search?sensor=hq-core&search=srch_000000000000')

  await expect(page.getByText('Search not found')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/run it again/i)).toBeVisible()
  await expect(page.getByRole('table')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Run search' })).toBeEnabled()
})
