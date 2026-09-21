import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/dev/states')
})

test('announces work in progress', async ({ page }) => {
  await expect(page.getByRole('status')).toContainText('Loading sessions')
})

test('an empty result is not announced as a failure', async ({ page }) => {
  const empty = page.getByRole('region', { name: 'Empty' })
  await expect(empty).toContainText('No sessions match')
  await expect(empty.getByRole('alert')).toHaveCount(0)
})

test('a server failure can be retried', async ({ page }) => {
  const server = page.getByRole('region', { name: 'Server failure' })
  await expect(server.getByRole('alert')).toBeVisible()

  await server.getByRole('button', { name: 'Try again' }).click()

  await expect(page.getByTestId('retry-count')).toHaveText('retries: 1')
})

test('a permission failure and a gone session offer no retry', async ({ page }) => {
  await expect(page.getByRole('region', { name: 'No permission' }).getByRole('button')).toHaveCount(
    0,
  )
  await expect(page.getByRole('region', { name: 'Session gone' }).getByRole('button')).toHaveCount(
    0,
  )
})

test('a rate-limited failure waits out the delay the server asked for', async ({ page }) => {
  const button = page.getByRole('region', { name: 'Rate limited' }).getByRole('button')

  await expect(button).toBeDisabled()
  await expect(button).toContainText('Try again in')
  await expect(button).toBeEnabled({ timeout: 10_000 })
})

test('a toast carries a message without covering the page', async ({ page }) => {
  const notifications = page.getByRole('region', { name: 'Notifications' })

  await page.getByRole('button', { name: 'Show a toast' }).click()
  await expect(notifications.getByText('The slot is free again.')).toBeVisible()

  await notifications.getByRole('button', { name: 'Dismiss' }).click()
  await expect(notifications.getByText('The slot is free again.')).toHaveCount(0)
})
