'use client'

import { useEffect, useState } from 'react'

/**
 * The value once it has stopped changing. Used to keep a form from asking the server per keystroke:
 * the estimate endpoint allows only a few requests per second and counts the refusals against us.
 */
export function useDebounced<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return settled
}
