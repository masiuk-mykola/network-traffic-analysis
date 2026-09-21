import { expect, test, type Page } from '@playwright/test'

import { clickRun, dropSearch, watchSearches } from './search-flow'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

// An account has three search slots. These tests take them, so they run one at a time and give
// each one back — otherwise a later test is refused for want of a slot rather than for a bug.
test.describe.configure({ mode: 'serial' })

test.beforeEach(async ({ page }) => {
  watchSearches(page)
  // A job from an earlier test holds its slot until it is deleted, whatever state it ended in.
  await dropSearch(page)
})

test.afterEach(async ({ page }) => {
  await dropSearch(page)
})

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

async function readyQuery(page: Page) {
  await signIn(page)
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()
  await expect(page.getByRole('button', { name: 'Run search' })).toBeEnabled()
}

test('a search starts and says so', async ({ page }) => {
  await readyQuery(page)

  await clickRun(page)

  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page).toHaveURL(/search=/)
})

test('pressing twice starts one job, not two', async ({ page }) => {
  await readyQuery(page)

  const posts: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/api/searches')) {
      posts.push(request.url())
    }
  })

  const button = page.getByRole('button', { name: 'Run search' })
  await button.click()
  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })
  // The job reaches the address through the router, which lands a tick after the screen does.
  await expect(page).toHaveURL(/search=srch_/, { timeout: 15_000 })
  const first = new URL(page.url()).searchParams.get('search')

  // Nothing changed, so this is the same search — sending it again would be an identical body
  // seconds later, which the API counts as a duplicate job.
  await button.click()
  await page.waitForTimeout(500)

  expect(posts).toHaveLength(1)
  expect(new URL(page.url()).searchParams.get('search')).toBe(first)
})

test('the started search survives a reload', async ({ page }) => {
  await readyQuery(page)
  await clickRun(page)
  await expect(page).toHaveURL(/search=/)
  const url = page.url()

  await page.reload()

  expect(page.url()).toBe(url)
  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })
})

test('a changed query starts another search and frees the first slot', async ({ page }) => {
  await readyQuery(page)

  const verbs: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/searches')) verbs.push(request.method())
  })

  await clickRun(page)
  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })

  await page.getByRole('listitem').filter({ hasText: 'DC East' }).getByRole('checkbox').click()
  await clickRun(page)
  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })

  expect(verbs.filter((verb) => verb === 'DELETE')).toHaveLength(1)
})
