import { expect, test, type Page } from '@playwright/test'

const ANALYST = { email: 'ana@quillmere.example', password: 'demo-analyst' }

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ANALYST.email)
  await page.getByLabel('Password').fill(ANALYST.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/search/)
}

async function addCondition(page: Page) {
  await page.getByRole('button', { name: /add condition/i }).click()
}

async function choose(page: Page, label: string, option: string | RegExp, index = 0) {
  await page.getByRole('combobox', { name: label }).nth(index).click()
  await page.getByRole('option', { name: option }).click()
}

test('the fields come from the server, protocol-specific ones included', async ({ page }) => {
  await signIn(page)
  await addCondition(page)

  await page.getByRole('combobox', { name: 'Field' }).click()

  await expect(page.getByRole('option', { name: 'TLS SNI' })).toBeVisible()
  await expect(page.getByRole('option', { name: 'Source IP' })).toBeVisible()
})

test('a closed field offers the values the server publishes', async ({ page }) => {
  await signIn(page)
  await addCondition(page)
  await choose(page, 'Field', 'Protocol')
  await choose(page, 'Comparison', 'is')

  await page.getByRole('combobox', { name: 'Value' }).click()

  await expect(page.getByRole('option', { name: /dns/i })).toBeVisible()
})

test('a built condition survives a reload', async ({ page }) => {
  await signIn(page)
  await page.getByRole('listitem').filter({ hasText: 'HQ Core' }).getByRole('checkbox').click()
  await addCondition(page)
  await choose(page, 'Field', 'Protocol')
  await choose(page, 'Comparison', 'is')
  await choose(page, 'Value', /dns/i)

  await expect(page).toHaveURL(/f=protocol%3Aeq%3Adns|f=protocol:eq:dns/)
  await page.reload()

  await expect(page.getByRole('combobox', { name: 'Field' })).toHaveText('Protocol')
  await expect(page.getByRole('combobox', { name: 'Value' })).toHaveText(/dns/i)
})

test('the same closed field is asked for once, however many rows use it', async ({ page }) => {
  await signIn(page)

  const enumCalls: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('meta/enums/protocol')) enumCalls.push(request.url())
  })

  await addCondition(page)
  await choose(page, 'Field', 'Protocol')
  await choose(page, 'Comparison', 'is')
  await addCondition(page)
  await choose(page, 'Field', 'Protocol', 1)
  await choose(page, 'Comparison', 'is', 1)

  await expect(page.getByRole('combobox', { name: 'Value' }).nth(1)).toBeVisible()
  expect(enumCalls).toHaveLength(1)
})
