'use client'

import { ErrorState } from '@/components/states'

/**
 * The boundary for anything a screen or a layout throws. It lives at the root because an error.tsx
 * does not catch what the layout of its own segment throws, and the guard runs in a layout.
 *
 * Reaching here means the session was never disproved — the API was simply unreachable — so the
 * person keeps their session and is offered a retry.
 */
export default function AppError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <ErrorState error={error} onRetry={reset} variant="page" />
    </main>
  )
}
