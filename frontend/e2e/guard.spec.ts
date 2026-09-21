import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

async function signIn(page: Page) {
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test('a working screen is not reachable without a session', async ({ page }) => {
  await page.goto('/search')

  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})

test('signing in continues to where the visitor was going', async ({ page }) => {
  await page.goto('/sessions/72075232438042624')
  await expect(page).toHaveURL(/\/login\?next=/)

  await signIn(page)

  await expect(page).toHaveURL('/sessions/72075232438042624')
})

test('a destination pointing at another site is ignored', async ({ page }) => {
  await page.goto('/login?next=https%3A%2F%2Fevil.example')

  await signIn(page)

  await expect(page).toHaveURL(/\/search/)
})

test('the shell says who is signed in', async ({ page }) => {
  await page.goto('/login')
  await signIn(page)

  const header = page.getByRole('banner')
  await expect(header).toContainText('Ana Duarte')
  await expect(header).toContainText('analyst')
})

test('signing out asks first, then leaves nothing reachable', async ({ page }) => {
  await page.goto('/login')
  await signIn(page)
  await expect(page).toHaveURL(/\/search/)

  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Stay signed in' }).click()
  await expect(page).toHaveURL(/\/search/)

  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login/)

  // Back must not bring a guarded screen out of the history cache, and asking for one directly
  // must go through the guard again.
  await page.goBack()
  await expect(page.getByRole('banner')).toHaveCount(0)

  await page.goto('/search')
  await expect(page).toHaveURL(/\/login/)
})

test('nothing is asked of the old session after signing out', async ({ page }) => {
  await page.goto('/login')
  await signIn(page)

  const afterSignOut: string[] = []
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login/)

  page.on('request', (request) => {
    if (request.url().includes('/api/capture/')) afterSignOut.push(request.url())
  })
  await page.waitForTimeout(5_500)

  expect(afterSignOut).toEqual([])
})
