import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

async function pickPoint(page: Page, name: string) {
  await page.getByRole('listitem').filter({ hasText: name }).getByRole('checkbox').click()
}

test('a complete query is sized before it is run', async ({ page }) => {
  await signIn(page)
  await pickPoint(page, 'HQ Core')

  await expect(page.getByText(/sessions match/)).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText(/estimated from a sample/i)).toBeVisible()
})

test('an incomplete query is not sized at all', async ({ page }) => {
  const asked: string[] = []
  await signIn(page)
  page.on('request', (request) => {
    if (request.url().includes('/api/capture/estimate')) asked.push(request.url())
  })

  // No capture point chosen yet, so there is nothing to ask about.
  await page.waitForTimeout(1500)

  expect(asked).toEqual([])
})

test('a burst of changes does not become a burst of requests', async ({ page }) => {
  await signIn(page)
  const asked: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/capture/estimate')) asked.push(request.url())
  })

  // Four changes in quick succession, ending with a query that can be sized.
  await pickPoint(page, 'HQ Core')
  await pickPoint(page, 'DC East')
  await pickPoint(page, 'DC East')
  await pickPoint(page, 'DC East')
  await expect(page.getByText(/sessions match|No sessions match/)).toBeVisible({ timeout: 10_000 })

  // Four changes inside the settle delay; the endpoint allows four requests a second in total.
  expect(asked.length).toBeLessThanOrEqual(2)
})

test('a narrow condition brings the estimate down', async ({ page }) => {
  await signIn(page)
  await pickPoint(page, 'HQ Core')
  await expect(page.getByText(/sessions match/)).toBeVisible({ timeout: 10_000 })

  await page.getByRole('button', { name: /add condition/i }).click()
  await page.getByRole('combobox', { name: 'Field' }).click()
  await page.getByRole('option', { name: 'Protocol' }).click()
  await page.getByRole('combobox', { name: 'Comparison' }).click()
  await page.getByRole('option', { name: 'is' }).click()
  await page.getByRole('combobox', { name: 'Value' }).click()
  await page.getByRole('option', { name: /dns/i }).click()

  await expect(page.getByText(/sessions match|No sessions match/)).toBeVisible({ timeout: 10_000 })
})
