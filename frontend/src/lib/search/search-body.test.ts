import { describe, expect, it } from 'vitest'

import { emptyRow, type FieldCatalogue } from './condition'
import { EMPTY_QUERY, type QueryState } from './query-params'
import { idempotencyKeyFor, toSearchBody } from './search-body'

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
  sensorIds: ['hq-core'],
  from: '2025-10-27T06:00:00.000Z',
  to: '2025-10-27T12:00:00.000Z',
}

describe('toSearchBody', () => {
  it('sends what the endpoint requires', () => {
    expect(toSearchBody(READY, FIELDS)).toEqual({
      sensor_ids: ['hq-core'],
      from: READY.from,
      to: READY.to,
      filter: { all: [] },
      sort: '-ts',
    })
  })

  it('carries the conditions as the filter', () => {
    const state = {
      ...READY,
      conditions: [{ ...emptyRow(), field: 'protocol', op: 'eq', values: ['dns'] }],
    }

    expect(toSearchBody(state, FIELDS)?.filter).toEqual({
      all: [{ field: 'protocol', op: 'eq', value: 'dns' }],
    })
  })

  it('refuses a query that cannot be run', () => {
    expect(toSearchBody(EMPTY_QUERY, FIELDS)).toBeNull()
    expect(toSearchBody({ ...READY, sensorIds: [] }, FIELDS)).toBeNull()
    expect(toSearchBody({ ...READY, to: READY.from }, FIELDS)).toBeNull()
  })
})

describe('idempotencyKeyFor', () => {
  const body = toSearchBody(READY, FIELDS)!

  it('is the same label for the same query, so a retry replays instead of duplicating', () => {
    expect(idempotencyKeyFor(body)).toBe(idempotencyKeyFor(toSearchBody({ ...READY }, FIELDS)!))
  })

  it('is a different label once the query changes', () => {
    const narrowed = toSearchBody(
      { ...READY, conditions: [{ ...emptyRow(), field: 'protocol', op: 'eq', values: ['dns'] }] },
      FIELDS,
    )!

    expect(idempotencyKeyFor(narrowed)).not.toBe(idempotencyKeyFor(body))
  })

  it('looks the way the API demands', () => {
    expect(idempotencyKeyFor(body)).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
  })
})
