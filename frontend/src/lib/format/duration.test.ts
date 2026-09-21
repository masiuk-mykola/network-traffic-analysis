import { describe, expect, it } from 'vitest'

import { formatDuration } from './duration'
import { EMPTY } from './empty'

describe('formatDuration', () => {
  it('keeps milliseconds under a second, where this traffic lives', () => {
    expect(formatDuration(0)).toBe('0 ms')
    expect(formatDuration(840)).toBe('840 ms')
    expect(formatDuration(999)).toBe('999 ms')
  })

  it('switches to seconds at exactly one second', () => {
    expect(formatDuration(1000)).toBe('1.0 s')
    expect(formatDuration(2400)).toBe('2.4 s')
    expect(formatDuration(59_900)).toBe('59.9 s')
  })

  it('reads minutes and hours without losing the smaller unit', () => {
    expect(formatDuration(60_000)).toBe('1 m 00 s')
    expect(formatDuration(72_000)).toBe('1 m 12 s')
    expect(formatDuration(3_600_000)).toBe('1 h 00 m')
    expect(formatDuration(11_100_000)).toBe('3 h 05 m')
  })

  it('refuses a value that cannot be a duration', () => {
    expect(formatDuration(-1)).toBe(EMPTY)
    expect(formatDuration(Number.NaN)).toBe(EMPTY)
  })
})
