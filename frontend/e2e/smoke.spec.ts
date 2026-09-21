import { expect, test } from '@playwright/test'

test('the app opens at sign in', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})

test('signing in opens the search screen', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('ana@quillmere.example')
  await page.getByLabel('Password').fill('demo-analyst')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL('/search')
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
})
