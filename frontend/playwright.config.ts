import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  // An account holds three searches at a time; a spec that finds them taken waits out the delay the
  // server asks for, which can be longer than Playwright's own default.
  timeout: 90_000,
  // The API's limits are per account, not per browser: three search slots, and signing out revokes
  // the account's session. Specs are therefore not independent and run one at a time.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
})
