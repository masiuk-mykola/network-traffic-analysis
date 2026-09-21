import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }
const OBSERVER = { email: 'oli@quillmere.example', password: 'demo-observer' }
const API = process.env.CAPTURE_API_URL ?? 'http://localhost:8700'
const ADMIN_TOKEN = process.env.CAP_ADMIN_TOKEN ?? 'lf-dev-admin'

// Revoking kills every session for that email, so these run one at a time and use the account the
// other specs leave alone.
test.describe.configure({ mode: 'serial' })

async function signIn(page: Page, who: { email: string; password: string }) {
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password').fill(who.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

/** Kills the session the way the world does: from the server, without telling the browser. */
async function revoke(page: Page, email: string) {
  const response = await page.request.post(`${API}/v1/__admin/revoke`, {
    headers: { 'x-admin-token': ADMIN_TOKEN },
    data: { email },
  })
  expect(response.status()).toBe(204)
}

async function signedInProbe(page: Page, who: { email: string; password: string }) {
  await page.goto('/login')
  await signIn(page, who)
  await expect(page).toHaveURL(/\/search/)
  await page.goto('/dev/session')
  await expect(page.getByTestId('probe-name')).toBeVisible()
}

test('a session that dies mid-use sends the person back to sign in', async ({ page }) => {
  await signedInProbe(page, OBSERVER)

  await revoke(page, OBSERVER.email)
  // One read on the dead session is all the app needs to notice.
  await page.getByRole('button', { name: 'Read again' }).click()

  await expect(page).toHaveURL(/\/login/)
  await expect(
    page.getByRole('region', { name: 'Notifications' }).getByText('Your session ended'),
  ).toBeVisible()
})

test('it remembers where the interruption happened', async ({ page }) => {
  await signedInProbe(page, OBSERVER)

  await revoke(page, OBSERVER.email)
  await page.getByRole('button', { name: 'Read again' }).click()

  await expect(page).toHaveURL(/next=%2Fdev%2Fsession/)
  await signIn(page, OBSERVER)
  await expect(page).toHaveURL('/dev/session')
})

test('nothing is asked of the dead session afterwards', async ({ page }) => {
  await signedInProbe(page, OBSERVER)

  await revoke(page, OBSERVER.email)
  await page.getByRole('button', { name: 'Read again' }).click()
  await expect(page).toHaveURL(/\/login/)

  const afterwards: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/capture/')) afterwards.push(request.url())
  })
  await page.waitForTimeout(6_000)

  expect(afterwards).toEqual([])
})

test('the next account does not inherit the previous one', async ({ page }) => {
  await signedInProbe(page, OBSERVER)
  await expect(page.getByTestId('probe-name')).toHaveText('Oliver Brandt')

  await revoke(page, OBSERVER.email)
  await page.getByRole('button', { name: 'Read again' }).click()
  await expect(page).toHaveURL(/\/login/)

  await signIn(page, ANALYST)
  await expect(page).toHaveURL('/dev/session')
  await expect(page.getByTestId('probe-name')).toHaveText('Ana Duarte')
})
