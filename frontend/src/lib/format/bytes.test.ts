import { describe, expect, it } from 'vitest'

import { formatByteCount, formatBytes } from './bytes'
import { EMPTY } from './empty'

describe('formatBytes', () => {
  it('counts whole bytes without a decimal', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(999)).toBe('999 B')
  })

  it('switches unit at the boundary', () => {
    expect(formatBytes(1000)).toBe('1.0 kB')
    expect(formatBytes(999_999)).toBe('1000.0 kB')
    expect(formatBytes(1_000_000)).toBe('1.0 MB')
  })

  it('reads at any magnitude', () => {
    expect(formatBytes(1_400_000)).toBe('1.4 MB')
    expect(formatBytes(3_200_000_000)).toBe('3.2 GB')
    expect(formatBytes(5_000_000_000_000)).toBe('5.0 TB')
  })

  it('refuses to invent a number', () => {
    expect(formatBytes(-1)).toBe(EMPTY)
    expect(formatBytes(Number.NaN)).toBe(EMPTY)
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe(EMPTY)
  })
})

describe('formatByteCount', () => {
  it('keeps both directions and their sum', () => {
    expect(formatByteCount({ up: 240_000, down: 1_200_000 })).toEqual({
      total: '1.4 MB',
      up: '240.0 kB',
      down: '1.2 MB',
    })
  })

  it('survives a missing pair', () => {
    expect(formatByteCount(null)).toEqual({ total: EMPTY, up: EMPTY, down: EMPTY })
  })
})
