import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { dropSearch, signIn, startSearch, watchSearches } from './search-flow'

// Reaching the results and a session means running a search, which holds one of three slots.
test.describe.configure({ mode: 'serial' })

/** The standard the task is measured against; anything beyond AA is a preference, not a defect. */
const STANDARD = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(STANDARD).analyze()
}

/** A failure that names the rule and the element is worth more than a bare count. */
function describe(violations: Awaited<ReturnType<typeof scan>>['violations']): string {
  return violations
    .map(
      (violation) =>
        `${violation.id} (${violation.impact}): ${violation.nodes.length} — ${violation.help}`,
    )
    .join('\n')
}

test.beforeEach(async ({ page }) => {
  watchSearches(page)
})

test.afterEach(async ({ page }) => {
  await dropSearch(page)
})

test('the sign-in screen has no accessibility violations', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByLabel('Email')).toBeVisible()

  const { violations } = await scan(page)
  expect(describe(violations), describe(violations)).toBe('')
})

test('the search screen has none, with results on it', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('grid', { name: 'Results' })).toBeVisible({ timeout: 20_000 })

  const { violations } = await scan(page)
  expect(describe(violations), describe(violations)).toBe('')
})

test('the session screen has none', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  await expect(page.getByRole('grid', { name: 'Results' })).toBeVisible({ timeout: 20_000 })

  await page.getByRole('row').nth(1).click()
  await expect(page.getByRole('region', { name: 'Session summary' })).toBeVisible({
    timeout: 15_000,
  })

  const { violations } = await scan(page)
  expect(describe(violations), describe(violations)).toBe('')
})

test('the results table is walkable from the keyboard alone', async ({ page }) => {
  await signIn(page)
  await startSearch(page)
  const grid = page.getByRole('grid', { name: 'Results' })
  await expect(grid).toBeVisible({ timeout: 20_000 })

  // One row at a time holds the tab stop, so Tab reaches the table rather than every loaded row.
  const rows = page.getByRole('row')
  await rows.nth(1).focus()
  await expect(rows.nth(1)).toBeFocused()

  await page.keyboard.press('ArrowDown')
  await expect(rows.nth(2)).toBeFocused()

  await page.keyboard.press('ArrowUp')
  await expect(rows.nth(1)).toBeFocused()

  // Enter opens the session the focused row names, the way a click on it would.
  const href = await rows.nth(1).getAttribute('href')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`${href}$`))
})
