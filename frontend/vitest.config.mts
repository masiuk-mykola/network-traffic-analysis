import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    tsconfigPaths: true,
    alias: { 'server-only': new URL('./src/test/server-only.ts', import.meta.url).pathname },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: './coverage',
      // Only code this repository is responsible for. Generated clients and the dev-only gallery
      // would move the number without saying anything about the tests.
      include: ['src'],
      // Only the logic is held to a number. Route handlers and server components read as zero
      // here because the e2e suite covers them and Vitest cannot see it, so a threshold over all
      // of `src` would demand unit tests where they prove very little.
      //
      // These sit just under what the suite achieves today: they catch a regression without
      // failing on a rounding wobble. Raise them when the figure rises, never lower them to pass.
      thresholds: {
        'src/lib/**': {
          statements: 88,
          branches: 85,
          functions: 92,
          lines: 90,
        },
      },
      exclude: ['src/lib/api/generated/**', 'src/app/dev/**', 'src/test/**', '**/*.d.ts'],
    },
  },
})
