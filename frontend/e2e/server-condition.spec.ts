import { expect, test, type Page } from '@playwright/test'

import { signIn } from './search-flow'

const DEGRADED = {
  status: 'degraded',
  components: {
    index: { status: 'degraded', detail: 'The session index is rebuilding; searches may be slow.' },
    decoder: { status: 'ok' },
    pcap_store: { status: 'ok' },
    live_feed: { status: 'ok' },
  },
  server_time: '2025-10-27T12:00:00.000Z',
  version: '1.0.0',
}

/**
 * The server reports a degraded part only under load, and this app deliberately rations the read and
 * keeps its failures silent — so driving this through the chaos profile would be a coin toss twice
 * over. The answer is intercepted instead, which is what the rest of the suite does with a path it
 * needs to control.
 */
async function report(page: Page, body: unknown) {
  await page.route('**/api/capture/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  )
}

test('a degraded part of the server is quoted above every screen', async ({ page }) => {
  await report(page, DEGRADED)
  await signIn(page)

  const notice = page.getByRole('status', { name: 'Server condition' })
  await expect(notice).toBeVisible({ timeout: 20_000 })
  await expect(notice).toContainText('index')
  await expect(notice).toContainText('The session index is rebuilding; searches may be slow.')

  // It explains; it does not take the screen over.
  await expect(page.getByRole('button', { name: 'Run search' })).toBeVisible()
})

test('and it can be dismissed for that condition', async ({ page }) => {
  await report(page, DEGRADED)
  await signIn(page)
  const notice = page.getByRole('status', { name: 'Server condition' })
  await expect(notice).toBeVisible({ timeout: 20_000 })

  await notice.getByRole('button', { name: 'Dismiss' }).click()

  await expect(page.getByRole('status', { name: 'Server condition' })).toHaveCount(0)
})

test('and nothing is said while the server is well', async ({ page }) => {
  await report(page, { ...DEGRADED, status: 'ok', components: { index: { status: 'ok' } } })
  await signIn(page)

  await expect(page.getByRole('listitem').filter({ hasText: 'HQ Core' })).toBeVisible({
    timeout: 20_000,
  })
  await expect(page.getByRole('status', { name: 'Server condition' })).toHaveCount(0)
})

test('an observer sees a sensitive value withheld, not printed', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('oli@quillmere.example')
  await page.getByLabel('Password').fill('demo-observer')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)

  // An HTTP session: the server replaces its cookie and authorization headers for an observer.
  // The simulator's clock starts at a fixed moment and runs with the process, and the capture ends
  // at its "now" — so the newest sessions exist only on a server that has been up for a while. This
  // one sits well inside the three days a freshly started one already holds; an id copied from a
  // long-running dev server would be in the future of the container CI starts, and 404 there.
  await page.goto('/sessions/72057637085118467')
  const main = page.getByRole('main')
  await expect(main.getByText('Withheld for your role').first()).toBeVisible({ timeout: 20_000 })
  await expect(main).not.toContainText('"redacted"')
})
