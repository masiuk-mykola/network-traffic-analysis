import { describe, expect, it } from 'vitest'

import { EMPTY } from './empty'
import { formatTimeOfDay, formatTimestamp } from './time'

const SAMPLE = '2025-10-27T09:14:03.120Z'

describe('formatTimestamp', () => {
  it('says which zone it is showing', () => {
    expect(formatTimestamp(SAMPLE)).toBe('2025-10-27 09:14:03.120 UTC')
  })

  it('shows UTC no matter where the machine is', () => {
    // The same instant written with an offset must read the same.
    expect(formatTimestamp('2025-10-27T11:14:03.120+02:00')).toBe(formatTimestamp(SAMPLE))
  })

  it('keeps the milliseconds the API sends', () => {
    expect(formatTimestamp('2025-10-27T09:14:03.007Z')).toContain('.007')
  })

  it('returns the raw input rather than an invalid date', () => {
    expect(formatTimestamp('27/10/2025 12:00:00')).toBe('27/10/2025 12:00:00')
    expect(formatTimestamp('')).toBe(EMPTY)
  })
})

describe('formatTimeOfDay', () => {
  it('drops the date for a dense cell but keeps the precision', () => {
    expect(formatTimeOfDay(SAMPLE)).toBe('09:14:03.120')
  })

  it('falls back like the full form', () => {
    expect(formatTimeOfDay('not a time')).toBe('not a time')
  })
})
