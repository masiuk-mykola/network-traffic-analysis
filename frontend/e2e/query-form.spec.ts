import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

test('the form lists the capture points this account can read', async ({ page }) => {
  await signIn(page)

  const points = page.getByRole('listitem')
  await expect(points).toHaveCount(3)
  await expect(points.first()).toContainText('HQ Core')
})

test('a point that is behind says so, and says how far', async ({ page }) => {
  await signIn(page)

  // One of the three points in this capture runs minutes behind the others.
  const lagging = page.getByRole('listitem').filter({ hasText: /behind/i })
  await expect(lagging).toHaveCount(1)
  await expect(lagging).toContainText(/behind \d/)
})

test('the suggested window lands on traffic that exists', async ({ page }) => {
  await signIn(page)

  // The capture ends in 2025; a window built from today would return nothing.
  await expect(page.getByLabel('To (UTC)')).toHaveValue(/^2025-10-27T/)
  await expect(page.getByText(/this capture ends at/i)).toBeVisible()
})

test('searching nowhere is refused before anything is sent', async ({ page }) => {
  await signIn(page)

  await expect(page.getByText('Choose at least one capture point.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run search' })).toBeDisabled()
})

test('the choices survive a reload', async ({ page }) => {
  await signIn(page)

  await page.getByRole('listitem').filter({ hasText: 'DC East' }).getByRole('checkbox').click()
  await expect(page).toHaveURL(/sensor=dc-east/)

  await page.reload()

  await expect(
    page.getByRole('listitem').filter({ hasText: 'DC East' }).getByRole('checkbox'),
  ).toBeChecked()
  await expect(page.getByRole('button', { name: 'Run search' })).toBeEnabled()
})
