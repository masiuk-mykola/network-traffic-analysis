import { describe, expect, it } from 'vitest'

import {
  zGetSearchResponse,
  zGetSearchResultsResponse,
  zGetSessionResponse,
} from './generated/zod.gen'
import { schemaForPath } from './response-schemas'

describe('schemaForPath', () => {
  it('matches a fixed path', () => {
    expect(schemaForPath('/v1/sensors')).toBeDefined()
    expect(schemaForPath('/v1/meta/fields')).toBeDefined()
  })

  it('matches a parameterized path, including a uint64 id', () => {
    expect(schemaForPath('/v1/sessions/72075232438042624')).toBe(zGetSessionResponse)
    expect(schemaForPath('/v1/meta/schema/dns')).toBeDefined()
  })

  it('tells a search apart from its results', () => {
    expect(schemaForPath('/v1/searches/7')).toBe(zGetSearchResponse)
    expect(schemaForPath('/v1/searches/7/results')).toBe(zGetSearchResultsResponse)
  })

  it('accepts a column type the contract never listed', () => {
    const body = {
      items: [
        {
          key: 'dst_country',
          label: 'Destination country',
          type: 'geo_hint',
          default_visible: false,
          sortable: false,
          width_hint: 140,
        },
      ],
    }

    expect(schemaForPath('/v1/meta/columns')?.safeParse(body).success).toBe(true)
  })

  it('still rejects a column list with a missing field', () => {
    const body = { items: [{ key: 'start', label: 'Start', type: 'ts' }] }

    expect(schemaForPath('/v1/meta/columns')?.safeParse(body).success).toBe(false)
  })

  it('leaves an unmapped path unvalidated rather than guessing', () => {
    expect(schemaForPath('/v1/hunts')).toBeUndefined()
    expect(schemaForPath('/v1/sessions/7/pcap')).toBeUndefined()
    expect(schemaForPath('/v1/sessions')).toBeUndefined()
  })

  it('does not match a path that merely starts the same way', () => {
    expect(schemaForPath('/v1/sensors/extra')).toBeUndefined()
  })
})
