import { notFound } from 'next/navigation'

import { SessionProbe } from './session-probe'

/**
 * Exercises the real read path while the working screens are still placeholders, so the reaction to
 * a dead session can be driven end to end. Never in production.
 */
export default function SessionProbePage() {
  if (process.env.NODE_ENV === 'production') notFound()

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-4 p-6">
      <h1 className="text-xl font-semibold">Session probe</h1>
      <SessionProbe />
    </main>
  )
}
