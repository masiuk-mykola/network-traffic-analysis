import { describe, expect, it } from 'vitest'

import { isRedacted, WITHHELD } from './redacted'

describe('isRedacted', () => {
  it('recognises the marker the server puts in place of a value', () => {
    expect(isRedacted({ redacted: true })).toBe(true)
  })

  it('is not fooled by a value that merely mentions it', () => {
    expect(isRedacted('redacted')).toBe(false)
    expect(isRedacted({ redacted: false })).toBe(false)
    expect(isRedacted({ name: 'Cookie', value: 'sid=1' })).toBe(false)
    expect(isRedacted(null)).toBe(false)
    expect(isRedacted([{ redacted: true }])).toBe(false)
  })

  it('says why, not just that', () => {
    expect(WITHHELD).toMatch(/role/i)
  })
})
