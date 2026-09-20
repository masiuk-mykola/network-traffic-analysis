import { expect, test } from '@playwright/test'

test('search page opens', async ({ page }) => {
  await page.goto('/search')
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
})

test('root redirects to search', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL('/search')
})
