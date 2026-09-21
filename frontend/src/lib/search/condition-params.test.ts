import { describe, expect, it } from 'vitest'

import { conditionsToParams, parseConditions } from './condition-params'
import { emptyRow, type ConditionRow, type FieldCatalogue } from './condition'

const CATALOGUE: FieldCatalogue = {
  'src.ip': {
    name: 'src.ip',
    label: 'Source IP',
    type: 'ip',
    operators: ['eq', 'cidr', 'exists'],
    example: '10.0.0.1',
  },
  'http.user_agent': {
    name: 'http.user_agent',
    label: 'User agent',
    type: 'string',
    operators: ['eq', 'glob'],
    example: 'Mozilla/5.0',
  },
  'dst.port': {
    name: 'dst.port',
    label: 'Destination port',
    type: 'port',
    operators: ['eq', 'between'],
    example: '443',
  },
}

const row = (over: Partial<ConditionRow>): ConditionRow => ({ ...emptyRow(), ...over })

function roundTrip(rows: ConditionRow[]) {
  const params = new URLSearchParams()
  for (const value of conditionsToParams(rows)) params.append('f', value)
  // The identity is generated per row, so compare everything else.
  return parseConditions(params, CATALOGUE).map((row) => ({
    field: row.field,
    op: row.op,
    values: row.values,
    negated: row.negated,
  }))
}

describe('condition params', () => {
  it('writes and reads a row unchanged', () => {
    const rows = [row({ field: 'src.ip', op: 'eq', values: ['10.0.0.1'], negated: false })]

    expect(roundTrip(rows)).toEqual([
      { field: 'src.ip', op: 'eq', values: ['10.0.0.1'], negated: false },
    ])
  })

  it('keeps a range as two values', () => {
    const rows = [row({ field: 'dst.port', op: 'between', values: ['1024', '65535'] })]

    expect(roundTrip(rows)[0]).toMatchObject({ values: ['1024', '65535'] })
  })

  it('survives a value that contains the separators', () => {
    const ugly = 'Mozilla/5.0 (X11; Linux), rv:1.0'
    const rows = [row({ field: 'http.user_agent', op: 'glob', values: [ugly] })]

    expect(roundTrip(rows)[0]?.values).toEqual([ugly])
  })

  it('carries a negation', () => {
    const rows = [row({ field: 'src.ip', op: 'eq', values: ['10.0.0.1'], negated: true })]

    expect(roundTrip(rows)[0]?.negated).toBe(true)
  })

  it('writes nothing for an unfinished row', () => {
    expect(conditionsToParams([row({ field: '', op: '', values: [] })])).toEqual([])
  })

  it('drops a link that names a field this server does not publish', () => {
    const params = new URLSearchParams([['f', 'made.up:eq:x']])

    expect(parseConditions(params, CATALOGUE)).toEqual([])
  })

  it('drops an operator the field does not allow', () => {
    const params = new URLSearchParams([['f', 'src.ip:glob:10.*']])

    expect(parseConditions(params, CATALOGUE)).toEqual([])
  })

  it('drops something that is not a condition at all', () => {
    const params = new URLSearchParams([
      ['f', 'nonsense'],
      ['f', ''],
      ['f', 'src.ip::'],
    ])

    expect(parseConditions(params, CATALOGUE)).toEqual([])
  })

  it('gives every parsed row its own identity', () => {
    const params = new URLSearchParams([
      ['f', 'src.ip:eq:10.0.0.1'],
      ['f', 'src.ip:eq:10.0.0.2'],
    ])

    const [first, second] = parseConditions(params, CATALOGUE)
    expect(first?.id).not.toBe(second?.id)
  })
})
