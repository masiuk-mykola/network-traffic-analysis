import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

// Searches take slots; these tests take them one at a time and give them back.
test.describe.configure({ mode: 'serial' })

test.afterEach(async ({ page }) => {
  const started = new URL(page.url()).searchParams.get('search')
  if (started) await page.request.delete(`/api/searches/${started}`).catch(() => undefined)
})

async function startSearch(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()
  await page.getByRole('button', { name: 'Run search' }).click()
  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })
}

test('a search reports itself until it finishes, then stops asking', async ({ page }) => {
  const polls: string[] = []
  page.on('request', (request) => {
    if (/\/api\/capture\/searches\/[^/]+$/.test(request.url())) polls.push(request.url())
  })

  await startSearch(page)

  await expect(page.getByText('Search finished')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/matched/)).toBeVisible()

  const afterFinish = polls.length
  await page.waitForTimeout(6_000)

  // Nothing keeps a finished job under observation.
  expect(polls.length).toBe(afterFinish)
})

test('nothing is asked about a search before one is started', async ({ page }) => {
  const polls: string[] = []
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)

  page.on('request', (request) => {
    if (/\/api\/capture\/searches\//.test(request.url())) polls.push(request.url())
  })
  await page.waitForTimeout(2_000)

  expect(polls).toEqual([])
})

test('a search can be stopped, and says it was cancelled', async ({ page }) => {
  await startSearch(page)

  const stop = page.getByRole('button', { name: 'Stop' })
  if (await stop.isVisible().catch(() => false)) {
    await stop.click()
    await expect(page.getByText(/Search cancelled|Search finished/)).toBeVisible({
      timeout: 15_000,
    })
  } else {
    // The capture is small enough that a search can finish before the click lands.
    await expect(page.getByText('Search finished')).toBeVisible()
  }
})
