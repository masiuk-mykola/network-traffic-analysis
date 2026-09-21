import { describe, expect, it } from 'vitest'

import { EMPTY_QUERY, parseQuery, toQueryString, MAX_SENSORS } from './query-params'

const READABLE = ['hq-core', 'dc-east', 'harbor-branch']
const WINDOW = { from: '2025-10-27T06:00:00.000Z', to: '2025-10-27T12:00:00.000Z' }

function parse(search: string, readable: string[] = READABLE) {
  return parseQuery(new URLSearchParams(search), readable)
}

describe('parseQuery', () => {
  it('reads sensors given one by one or comma-joined', () => {
    expect(parse('sensor=hq-core&sensor=dc-east').sensorIds).toEqual(['hq-core', 'dc-east'])
    expect(parse('sensor=hq-core,dc-east').sensorIds).toEqual(['hq-core', 'dc-east'])
  })

  it('drops a point this account cannot read', () => {
    expect(parse('sensor=hq-core&sensor=somewhere-else').sensorIds).toEqual(['hq-core'])
  })

  it('drops repeats rather than counting them twice', () => {
    expect(parse('sensor=hq-core&sensor=hq-core').sensorIds).toEqual(['hq-core'])
  })

  it('clips a link that carries more than the API accepts', () => {
    const many = Array.from({ length: 8 }, (_, i) => `s${i}`)
    const state = parseQuery(new URLSearchParams(many.map((id) => ['sensor', id])), many)

    expect(state.sensorIds).toHaveLength(MAX_SENSORS)
  })

  it('keeps a window that makes sense', () => {
    const state = parse(`from=${WINDOW.from}&to=${WINDOW.to}`)

    expect(state).toMatchObject(WINDOW)
  })

  it('drops a window that is backwards or unreadable', () => {
    expect(parse(`from=${WINDOW.to}&to=${WINDOW.from}`).from).toBeNull()
    expect(parse('from=yesterday&to=today').from).toBeNull()
    expect(parse(`from=${WINDOW.from}`).to).toBeNull()
  })

  it('survives an empty query', () => {
    expect(parse('')).toEqual(EMPTY_QUERY)
  })
})

describe('toQueryString', () => {
  it('writes what it read', () => {
    const state = { ...EMPTY_QUERY, sensorIds: ['hq-core', 'dc-east'], ...WINDOW }

    expect(parse(toQueryString(state))).toEqual(state)
  })

  it('leaves out what is not set', () => {
    expect(toQueryString(EMPTY_QUERY)).toBe('')
  })
})

describe('the order in the address', () => {
  it('reads one the server publishes and ignores anything else', () => {
    expect(parseQuery(new URLSearchParams('sort=-bytes')).sort).toBe('-bytes')
    expect(parseQuery(new URLSearchParams('sort=summary')).sort).toBe('-ts')
    expect(parseQuery(new URLSearchParams('')).sort).toBe('-ts')
  })

  it('writes it only when it is not the default', () => {
    const base = { ...EMPTY_QUERY, sensorIds: ['hq-core'] }

    expect(toQueryString({ ...base, sort: '-ts' })).not.toContain('sort')
    expect(toQueryString({ ...base, sort: 'risk' })).toContain('sort=risk')
  })
})
