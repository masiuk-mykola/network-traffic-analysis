'use client'

import { useEffect, useState } from 'react'

const SECOND_MS = 1000

/**
 * Counts a server-advertised wait down to zero, so nothing in the UI can repeat a request the
 * server just refused. Seeded once per mount: a different failure arrives as a new element.
 */
export function useCountdown(waitMs: number | null): number {
  const [remaining, setRemaining] = useState(() =>
    waitMs !== null && waitMs > 0 ? Math.ceil(waitMs / SECOND_MS) : 0,
  )

  useEffect(() => {
    if (remaining <= 0) return
    const timer = setInterval(() => {
      setRemaining((seconds) => (seconds <= 1 ? 0 : seconds - 1))
    }, SECOND_MS)
    return () => clearInterval(timer)
  }, [remaining])

  return remaining
}
