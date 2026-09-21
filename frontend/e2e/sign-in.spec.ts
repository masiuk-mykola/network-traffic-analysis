import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

async function signIn(page: Page, email: string, password: string) {
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test('signing in lands on the search screen', async ({ page }) => {
  await page.goto('/login')

  await signIn(page, ANALYST.email, ANALYST.password)

  await expect(page).toHaveURL(/\/search/)
  await expect(page.getByRole('heading', { name: 'Search' })).toBeVisible()
})

test('the whole form works from the keyboard alone', async ({ page }) => {
  await page.goto('/login')

  await page.getByLabel('Email').focus()
  await page.keyboard.type(ANALYST.email)
  await page.keyboard.press('Tab')
  await page.keyboard.type(ANALYST.password)
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/\/search/)
})

test('no API token reaches the browser', async ({ page }) => {
  await page.goto('/login')

  const loginResponse = page.waitForResponse((res) => res.url().includes('/api/auth/login'))
  await signIn(page, ANALYST.email, ANALYST.password)
  const body = await (await loginResponse).text()

  expect(body).not.toMatch(/access_token|refresh_token|bearer/i)

  await expect(page).toHaveURL(/\/search/)
  const stored = await page.evaluate(() => ({
    local: JSON.stringify(localStorage),
    session: JSON.stringify(sessionStorage),
    cookies: document.cookie,
  }))
  expect(`${stored.local}${stored.session}${stored.cookies}`).not.toMatch(
    /access_token|refresh_token|bearer|demo-analyst/i,
  )
})

test('a wrong password is refused without saying whether the email is known', async ({ page }) => {
  await page.goto('/login')

  await signIn(page, ANALYST.email, 'not-the-password')

  const alert = page.getByRole('alert')
  await expect(alert).toBeVisible()
  await expect(alert).not.toContainText(ANALYST.email)
  await expect(page).toHaveURL(/\/login/)
})

test('an already signed-in visitor is sent onward', async ({ page }) => {
  await page.goto('/login')
  await signIn(page, ANALYST.email, ANALYST.password)
  await expect(page).toHaveURL(/\/search/)

  await page.goto('/login')

  await expect(page).toHaveURL(/\/search/)
})

test('the server stops accepting attempts, and the form stops offering them', async ({ page }) => {
  // The API allows five failures per email per minute; the sixth is refused with a stated wait.
  await page.goto('/login')
  const email = `rate-limit-${Date.now()}@quillmere.example`

  for (let attempt = 0; attempt < 6; attempt += 1) {
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill('wrong')
    const button = page.getByRole('button', { name: /sign in|try again in/i })
    if (await button.isEnabled()) await button.click()
    await expect(page.getByRole('alert')).toBeVisible()
  }

  await expect(page.getByRole('button', { name: /try again in \d+ s/i })).toBeDisabled()
})
