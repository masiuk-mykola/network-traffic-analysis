import { describe, expect, it } from 'vitest'

import type { FieldCatalogue } from './condition'
import { emptyRow } from './condition'
import { toEstimateParams } from './estimate-params'
import { EMPTY_QUERY, type QueryState } from './query-params'

const FIELDS: FieldCatalogue = {
  protocol: {
    name: 'protocol',
    label: 'Protocol',
    type: 'enum',
    operators: ['eq'],
    enum_name: 'protocol',
    example: 'dns',
  },
}

const READY: QueryState = {
  ...EMPTY_QUERY,
  sensorIds: ['hq-core', 'dc-east'],
  from: '2025-10-27T06:00:00.000Z',
  to: '2025-10-27T12:00:00.000Z',
}

describe('toEstimateParams', () => {
  it('asks for the window and the points the query names', () => {
    const params = toEstimateParams(READY, FIELDS)

    expect(params?.get('from')).toBe(READY.from)
    expect(params?.get('to')).toBe(READY.to)
    expect(params?.get('sensors')).toBe('hq-core,dc-east')
  })

  it('carries a finished condition in the shorthand the endpoint takes', () => {
    const state = {
      ...READY,
      conditions: [{ ...emptyRow(), field: 'protocol', op: 'eq', values: ['dns'] }],
    }

    expect(toEstimateParams(state, FIELDS)?.getAll('f')).toEqual(['protocol:eq:dns'])
  })

  it('asks for nothing while the query cannot be run', () => {
    expect(toEstimateParams(EMPTY_QUERY, FIELDS)).toBeNull()
    expect(toEstimateParams({ ...READY, sensorIds: [] }, FIELDS)).toBeNull()
    expect(toEstimateParams({ ...READY, from: null }, FIELDS)).toBeNull()
    expect(toEstimateParams({ ...READY, from: READY.to, to: READY.from }, FIELDS)).toBeNull()
  })

  it('asks for nothing while a condition is unfinished', () => {
    const state = {
      ...READY,
      conditions: [{ ...emptyRow(), field: 'protocol', op: 'eq', values: [] }],
    }

    expect(toEstimateParams(state, FIELDS)).toBeNull()
  })

  it('produces the same string for the same query, so it can be a cache key', () => {
    expect(toEstimateParams(READY, FIELDS)?.toString()).toBe(
      toEstimateParams({ ...READY }, FIELDS)?.toString(),
    )
  })
})
