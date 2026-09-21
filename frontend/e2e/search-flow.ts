import { expect, type Page } from '@playwright/test'

export const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

/** An account has three search slots, and a suite of specs can find them all taken for a moment. */
const RETRY_AFTER_MS = 6_000

export async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

const started = new Set<string>()

/**
 * Every job this test touches, so the slot goes back even when the address never named it — the
 * job reaches the address through the router, a tick after the screen.
 */
export function watchSearches(page: Page) {
  started.clear()
  page.on('request', (request) => {
    const match = /\/api\/(?:capture\/)?searches\/(srch_[a-z0-9]+)/.exec(request.url())
    if (match?.[1]) started.add(match[1])
  })
}

/** Start a search on one capture point, waiting out a refusal for want of a slot as a person would. */
export async function startSearch(page: Page) {
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()
  await page.getByRole('button', { name: 'Run search' }).click()

  const progress = page.getByRole('region', { name: 'Search progress' })
  const refused = page.getByRole('alert').filter({ hasText: 'Too many requests' })

  await expect(progress.or(refused).first()).toBeVisible({ timeout: 15_000 })
  if (await refused.isVisible()) {
    await page.waitForTimeout(RETRY_AFTER_MS)
    await page.getByRole('button', { name: 'Run search' }).click()
    await expect(progress).toBeVisible({ timeout: 15_000 })
  }

  await expect(page).toHaveURL(/search=srch_/, { timeout: 15_000 })
}

/**
 * Hand the slots back, whatever the test did with them — including tests that end on another
 * screen, where the address no longer names the job.
 */
export async function dropSearch(page: Page) {
  const fromAddress = new URL(page.url()).searchParams.get('search')
  if (fromAddress) started.add(fromAddress)

  const ids = [...started]
  started.clear()
  for (const id of ids) {
    await page.request.delete(`/api/searches/${id}`).catch(() => undefined)
  }
}
