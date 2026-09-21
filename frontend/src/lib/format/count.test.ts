import { describe, expect, it } from 'vitest'

import { formatApproximate, formatCount } from './count'

describe('formatCount', () => {
  it('groups thousands so a large number can be read', () => {
    expect(formatCount(98_142)).toBe('98,142')
    expect(formatCount(0)).toBe('0')
  })
})

describe('formatApproximate', () => {
  it('leaves a small number alone, because it is not really an estimate at that size', () => {
    expect(formatApproximate(0)).toBe('0')
    expect(formatApproximate(47)).toBe('47')
    expect(formatApproximate(999)).toBe('999')
  })

  it('rounds a large number to two significant figures', () => {
    expect(formatApproximate(1_000)).toBe('1,000')
    expect(formatApproximate(12_431)).toBe('12,000')
    expect(formatApproximate(98_142)).toBe('98,000')
    expect(formatApproximate(1_234_567)).toBe('1,200,000')
  })

  it('refuses to invent a number', () => {
    expect(formatApproximate(Number.NaN)).toBe('—')
    expect(formatApproximate(-1)).toBe('—')
  })
})
