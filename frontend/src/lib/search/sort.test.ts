import { describe, expect, it } from 'vitest'

import { DEFAULT_SORT, directionOf, parseSortKey, sortFieldFor, toggleSort } from './sort'

describe('parseSortKey', () => {
  it('accepts what the server publishes', () => {
    expect(parseSortKey('-ts')).toBe('-ts')
    expect(parseSortKey('bytes')).toBe('bytes')
  })

  it('drops anything else rather than failing', () => {
    expect(parseSortKey('summary')).toBeNull()
    expect(parseSortKey('')).toBeNull()
    expect(parseSortKey(null)).toBeNull()
  })
})

describe('sortFieldFor', () => {
  it('maps a published column to the field the server sorts on', () => {
    expect(sortFieldFor('start')).toBe('ts')
    expect(sortFieldFor('bytes')).toBe('bytes')
    expect(sortFieldFor('risk')).toBe('risk')
  })

  it('has no field for a column the server cannot sort', () => {
    expect(sortFieldFor('summary')).toBeNull()
  })
})

describe('directionOf', () => {
  it('reads the direction of the column in force, and nothing for the others', () => {
    expect(directionOf('-bytes', 'bytes')).toBe('descending')
    expect(directionOf('bytes', 'bytes')).toBe('ascending')
    expect(directionOf('-bytes', 'start')).toBeNull()
    expect(directionOf('summary' as never, 'summary')).toBeNull()
  })
})

describe('toggleSort', () => {
  it('starts a new column at the most interesting end', () => {
    expect(toggleSort(DEFAULT_SORT, 'bytes')).toBe('-bytes')
    expect(toggleSort(DEFAULT_SORT, 'risk')).toBe('-risk')
  })

  it('flips the column already in force', () => {
    expect(toggleSort('-bytes', 'bytes')).toBe('bytes')
  })

  it('returns to the default once it is flipped back off', () => {
    expect(toggleSort('bytes', 'bytes')).toBe(DEFAULT_SORT)
  })

  it('leaves the order alone for a column that cannot be sorted', () => {
    expect(toggleSort('-bytes', 'summary')).toBe('-bytes')
  })
})
