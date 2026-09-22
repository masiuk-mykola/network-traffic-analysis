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

  // The capture ends in the past, so a window built from the clock would return nothing. The end
  // is whatever the points last reported — read here rather than pinned to a date, because the
  // simulator walks that moment forward and a hardcoded day stops being true overnight.
  const answer = await page.request.get('/api/capture/sensors')
  expect(answer.ok()).toBe(true)
  const { items } = (await answer.json()) as { items: Array<{ last_packet_at?: string }> }
  const latest = items
    .map((sensor) => sensor.last_packet_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1)

  expect(latest).toBeDefined()
  // The control holds seconds; the API reports milliseconds.
  await expect(page.getByLabel('To (UTC)')).toHaveValue(latest!.slice(0, 19))
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
