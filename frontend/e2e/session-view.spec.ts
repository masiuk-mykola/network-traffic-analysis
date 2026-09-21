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
