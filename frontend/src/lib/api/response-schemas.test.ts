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

  it('leaves an unmapped path unvalidated rather than guessing', () => {
    expect(schemaForPath('/v1/hunts')).toBeUndefined()
    expect(schemaForPath('/v1/sessions/7/pcap')).toBeUndefined()
    expect(schemaForPath('/v1/sessions')).toBeUndefined()
  })

  it('does not match a path that merely starts the same way', () => {
    expect(schemaForPath('/v1/sensors/extra')).toBeUndefined()
  })
})
