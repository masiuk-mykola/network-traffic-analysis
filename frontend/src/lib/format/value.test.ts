import { describe, expect, it } from 'vitest'

import { EMPTY } from './empty'
import { formatByColumnType } from './value'

const WIDE_ID = '72075232438042624'

describe('formatByColumnType', () => {
  it('renders each documented kind through its own formatter', () => {
    expect(formatByColumnType('ts', '2025-10-27T09:14:03.120Z')).toBe('2025-10-27 09:14:03.120 UTC')
    expect(formatByColumnType('duration', 2400)).toBe('2.4 s')
    expect(formatByColumnType('bytes', { up: 240_000, down: 1_200_000 })).toBe('1.4 MB')
    expect(formatByColumnType('ip_port', { ip: '10.12.3.4', port: 443 })).toBe('10.12.3.4:443')
  })

  it('shows a risk score with the band the API assigned', () => {
    expect(formatByColumnType('risk', { score: 72, band: 'high' })).toBe('72 (high)')
  })

  it('shows an identifier character for character', () => {
    expect(formatByColumnType('id', WIDE_ID)).toBe(WIDE_ID)
  })

  it('shows enum-like kinds the way the API spells them', () => {
    expect(formatByColumnType('protocol', 'dns')).toBe('dns')
    expect(formatByColumnType('country', 'PT')).toBe('PT')
    expect(formatByColumnType('sensor', 'hq-core')).toBe('hq-core')
  })

  it('falls back to text for a kind the API has not documented', () => {
    expect(formatByColumnType('something-new', 'value')).toBe('value')
    expect(formatByColumnType('something-new', 42)).toBe('42')
  })

  it('marks an absent value instead of leaving a blank cell', () => {
    expect(formatByColumnType('text', null)).toBe(EMPTY)
    expect(formatByColumnType('text', undefined)).toBe(EMPTY)
    expect(formatByColumnType('text', '')).toBe(EMPTY)
    expect(formatByColumnType('duration', 0)).not.toBe(EMPTY)
  })

  it('does not throw on a value of the wrong shape', () => {
    expect(formatByColumnType('ts', 12345)).toBe('12345')
    expect(formatByColumnType('bytes', 'lots')).toBe('lots')
    expect(formatByColumnType('ip_port', 'nowhere')).toBe('nowhere')
  })
})
