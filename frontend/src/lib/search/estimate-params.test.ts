import { describe, expect, it } from 'vitest'

import type { FieldCatalogue } from './condition'
import { emptyRow } from './condition'
import { describeEstimateGap, toEstimateParams } from './estimate-params'
import { EMPTY_QUERY, type QueryState } from './query-params'

const FIELDS: FieldCatalogue = {
  'src.ip': {
    name: 'src.ip',
    label: 'Source IP',
    type: 'ip',
    operators: ['eq'],
    example: '10.0.0.1',
  },
  'dst.ip': {
    name: 'dst.ip',
    label: 'Destination IP',
    type: 'ip',
    operators: ['eq'],
    example: '10.0.0.2',
  },
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

  it('does not ask a question the endpoint cannot express', () => {
    // The endpoint ANDs its filters and takes no join, so an any-joined pair would be estimated as
    // an impossible conjunction.
    const state = {
      ...READY,
      join: 'any' as const,
      conditions: [
        { ...emptyRow(), field: 'src.ip', op: 'eq', values: ['10.20.40.18'] },
        { ...emptyRow(), field: 'dst.ip', op: 'eq', values: ['10.20.40.18'] },
      ],
    }

    expect(toEstimateParams(state, FIELDS)).toBeNull()
    expect(describeEstimateGap(state)).toMatch(/any/i)
  })

  it('still asks when a single condition is joined with any, which means nothing', () => {
    const state = {
      ...READY,
      join: 'any' as const,
      conditions: [{ ...emptyRow(), field: 'protocol', op: 'eq', values: ['dns'] }],
    }

    expect(toEstimateParams(state, FIELDS)?.getAll('f')).toEqual(['protocol:eq:dns'])
    expect(describeEstimateGap(state)).toBeNull()
  })

  it('still asks when the same pair is joined with all', () => {
    const state = {
      ...READY,
      conditions: [
        { ...emptyRow(), field: 'src.ip', op: 'eq', values: ['10.20.40.18'] },
        { ...emptyRow(), field: 'protocol', op: 'eq', values: ['dns'] },
      ],
    }

    expect(toEstimateParams(state, FIELDS)?.getAll('f')).toHaveLength(2)
    expect(describeEstimateGap(state)).toBeNull()
  })

  it('explains nothing while the query is merely unfinished', () => {
    expect(describeEstimateGap(EMPTY_QUERY)).toBeNull()
  })

  it('produces the same string for the same query, so it can be a cache key', () => {
    expect(toEstimateParams(READY, FIELDS)?.toString()).toBe(
      toEstimateParams({ ...READY }, FIELDS)?.toString(),
    )
  })
})
