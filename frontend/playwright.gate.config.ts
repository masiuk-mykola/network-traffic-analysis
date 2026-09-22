import { defineConfig, devices } from '@playwright/test'

/**
 * The traffic generator, which is not part of the suite.
 *
 * `npm run test:e2e` collects `*.spec.ts` only, so the `*-gate.ts` files are invisible to it by name
 * alone — this config exists to run them deliberately, one at a time. They drive minutes of traffic
 * under a chaos profile and take the account's search slots, so they must never run beside the
 * suite: the limits they exhaust are per account, not per browser.
 */
export default defineConfig({
  testDir: './e2e',
  // Every gate, and only the gates: `npm run test:e2e` collects `*.spec.ts` and never sees these.
  testMatch: /.*-gate\.ts$/,
  // Minutes of traffic under a profile that adds up to 1.5 s of latency to every read.
  timeout: 15 * 60_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    // The generator is run by hand against a dev server the operator already has up, which is why
    // the address is not fixed: step 1 of the plan runs it against an instrumented one.
    baseURL: process.env.GATE_BASE_URL ?? 'http://localhost:3000',
    trace: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: process.env.GATE_BASE_URL ?? 'http://localhost:3000',
    reuseExistingServer: true,
  },
})
