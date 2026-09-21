import { expect, type Page } from '@playwright/test'

export const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

/** An account has three search slots, and a suite of specs can find them all taken for a while. */
const ATTEMPTS = 3
const WAIT_MS = 45_000

export async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

const started = new Set<string>()
let pending: Array<Promise<void>> = []

/**
 * Every job this worker has touched, so a slot goes back even when the address never named it (the
 * job reaches the address a tick after the screen) and even when the test that started it failed
 * before its own cleanup ran. Deleting one twice is harmless.
 */
export function watchSearches(page: Page) {
  page.on('request', (request) => {
    const match = /\/api\/(?:capture\/)?searches\/(srch_[a-z0-9]+)/.exec(request.url())
    if (match?.[1]) started.add(match[1])
  })

  // The creation answer names the job even when the screen never gets as far as reading it.
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (response.request().method() !== 'POST' || url.pathname !== '/api/searches') return
    pending.push(
      response
        .json()
        .then((body: { id?: string }) => {
          if (body.id) started.add(body.id)
        })
        .catch(() => undefined),
    )
  })
}

/**
 * Press the run control, waiting out a refusal for want of a slot the way a person would: the
 * control counts out the delay the server asked for and offers itself again.
 */
export async function clickRun(page: Page) {
  const run = page.getByRole('button', { name: 'Run search' })
  const progress = page.getByRole('region', { name: 'Search progress' })
  const refused = page.getByRole('alert').filter({ hasText: 'Too many requests' })

  for (let attempt = 0; attempt < ATTEMPTS; attempt += 1) {
    await expect(run).toBeEnabled({ timeout: WAIT_MS })
    await run.click()
    await expect(progress.or(refused).first()).toBeVisible({ timeout: 15_000 })
    if (!(await refused.isVisible())) return
  }

  await expect(progress).toBeVisible({ timeout: 15_000 })
}

/** Start a search on one capture point. */
export async function startSearch(page: Page) {
  // A job from an earlier test in this worker still holds its slot until it is deleted, whatever
  // state it finished in. Hand those back before asking for another.
  await dropSearch(page)
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()

  await clickRun(page)

  await expect(page.getByRole('region', { name: 'Search progress' })).toBeVisible({
    timeout: 15_000,
  })
  await expect(page).toHaveURL(/search=srch_/, { timeout: 15_000 })
}

/**
 * Hand the slots back, whatever the test did with them — including tests that end on another
 * screen, where the address no longer names the job.
 */
export async function dropSearch(page: Page) {
  await Promise.all(pending)
  pending = []

  const fromAddress = new URL(page.url()).searchParams.get('search')
  if (fromAddress) started.add(fromAddress)

  const ids = [...started]
  started.clear()
  for (const id of ids) {
    await page.request.delete(`/api/searches/${id}`).catch(() => undefined)
  }
}
