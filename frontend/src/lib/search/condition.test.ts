import { describe, expect, it } from 'vitest'

import {
  describeCondition,
  emptyRow,
  toFilterNode,
  type ConditionRow,
  type FieldCatalogue,
} from './condition'

const FIELDS: FieldCatalogue = {
  'src.ip': {
    name: 'src.ip',
    label: 'Source IP',
    type: 'ip',
    operators: ['eq', 'cidr', 'exists'],
    example: '10.0.0.1',
  },
  'dst.port': {
    name: 'dst.port',
    label: 'Destination port',
    type: 'port',
    operators: ['eq', 'gte', 'lte', 'between'],
    example: '443',
  },
  protocol: {
    name: 'protocol',
    label: 'Protocol',
    type: 'enum',
    operators: ['eq', 'in'],
    enum_name: 'protocol',
    example: 'dns',
  },
}

const row = (over: Partial<ConditionRow> = {}): ConditionRow => ({
  ...emptyRow(),
  field: 'protocol',
  op: 'eq',
  values: ['dns'],
  ...over,
})

describe('toFilterNode', () => {
  it('joins the rows the way the switch says', () => {
    const rows = [row(), row({ field: 'src.ip', op: 'eq', values: ['10.0.0.1'] })]

    expect(toFilterNode(rows, 'all')).toEqual({
      all: [
        { field: 'protocol', op: 'eq', value: 'dns' },
        { field: 'src.ip', op: 'eq', value: '10.0.0.1' },
      ],
    })
    expect(toFilterNode(rows, 'any')).toHaveProperty('any')
  })

  it('wraps a negated row', () => {
    expect(toFilterNode([row({ negated: true })], 'all')).toEqual({
      all: [{ not: { field: 'protocol', op: 'eq', value: 'dns' } }],
    })
  })

  it('sends two values for a range and none for exists', () => {
    const between = row({ field: 'dst.port', op: 'between', values: ['1024', '65535'] })
    const exists = row({ field: 'src.ip', op: 'exists', values: [] })

    expect(toFilterNode([between], 'all', FIELDS)).toEqual({
      all: [{ field: 'dst.port', op: 'between', values: [1024, 65535] }],
    })
    expect(toFilterNode([exists], 'all', FIELDS)).toEqual({
      all: [{ field: 'src.ip', op: 'exists' }],
    })
  })

  it('sends a set as values', () => {
    const many = row({ op: 'in', values: ['dns', 'tls'] })

    expect(toFilterNode([many], 'all')).toEqual({
      all: [{ field: 'protocol', op: 'in', values: ['dns', 'tls'] }],
    })
  })

  it('keeps a numeric field numeric and a text field textual', () => {
    const port = row({ field: 'dst.port', op: 'eq', values: ['443'] })
    const ip = row({ field: 'src.ip', op: 'eq', values: ['10.0.0.1'] })

    expect(toFilterNode([port], 'all', FIELDS)).toEqual({
      all: [{ field: 'dst.port', op: 'eq', value: 443 }],
    })
    expect(toFilterNode([ip], 'all', FIELDS)).toEqual({
      all: [{ field: 'src.ip', op: 'eq', value: '10.0.0.1' }],
    })
  })

  it('has nothing to send when there are no rows', () => {
    expect(toFilterNode([], 'all')).toBeNull()
  })
})

describe('describeCondition', () => {
  const field = FIELDS['dst.port']

  it('accepts a finished row', () => {
    expect(
      describeCondition(row({ field: 'dst.port', op: 'eq', values: ['443'] }), field),
    ).toBeNull()
  })

  it('asks for a field first', () => {
    expect(describeCondition(row({ field: '', op: '', values: [] }))).toMatch(/field/i)
  })

  it('asks for a comparison', () => {
    expect(describeCondition(row({ field: 'dst.port', op: '', values: [] }), field)).toMatch(
      /comparison/i,
    )
  })

  it('refuses an operator the field does not allow', () => {
    expect(describeCondition(row({ field: 'dst.port', op: 'glob', values: ['x'] }), field)).toMatch(
      /does not allow/i,
    )
  })

  it('counts the values a range needs', () => {
    expect(
      describeCondition(row({ field: 'dst.port', op: 'between', values: ['1024'] }), field),
    ).toMatch(/two/i)
  })

  it('wants at least one value for a set, and not too many', () => {
    expect(describeCondition(row({ op: 'in', values: [] }), FIELDS.protocol)).toMatch(
      /at least one/i,
    )
    const tooMany = Array.from({ length: 51 }, (_, i) => `v${i}`)
    expect(describeCondition(row({ op: 'in', values: tooMany }), FIELDS.protocol)).toMatch(/50/)
  })

  it('wants exactly one value for everything else', () => {
    expect(describeCondition(row({ field: 'dst.port', op: 'eq', values: [] }), field)).toMatch(
      /a value/i,
    )
  })

  it('wants no value for exists', () => {
    expect(
      describeCondition(row({ field: 'src.ip', op: 'exists', values: [] }), FIELDS['src.ip']),
    ).toBeNull()
  })
})
