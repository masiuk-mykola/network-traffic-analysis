import { describe, expect, it } from 'vitest'

import {
  columnsKey,
  enumKey,
  estimateKey,
  fieldsKey,
  protocolSchemaKey,
  searchKey,
  searchResultsKey,
  sensorsKey,
  sessionFlowKey,
  sessionKey,
} from './keys'

describe('key factory', () => {
  it('returns the same key for the same inputs', () => {
    expect(searchResultsKey('7', '-bytes')).toEqual(searchResultsKey('7', '-bytes'))
    expect(sensorsKey()).toEqual(sensorsKey())
  })

  it('separates two different estimate queries', () => {
    expect(estimateKey('from=a&to=b')).not.toEqual(estimateKey('from=a&to=c'))
  })

  it('separates different inputs', () => {
    expect(sessionKey('72075232438042624')).not.toEqual(sessionKey('72075232438042625'))
    expect(searchResultsKey('7', '-bytes')).not.toEqual(searchResultsKey('7', 'bytes'))
    expect(enumKey('protocol')).not.toEqual(enumKey('risk'))
  })

  it('normalizes a missing optional argument instead of dropping it', () => {
    expect(searchResultsKey('7')).toEqual(searchResultsKey('7', undefined))
    expect(searchResultsKey('7')).toEqual(['search', '7', 'results', null])
    expect(sessionFlowKey('7')).toEqual(['session', '7', 'flow', null])
  })

  it('keeps each order of one search as its own entry, so a cursor cannot cross', () => {
    expect(searchResultsKey('7', '-ts')).not.toEqual(searchResultsKey('7', 'risk'))
    expect(searchResultsKey('7')).not.toEqual(searchResultsKey('7', '-ts'))
  })

  it('nests a result page under its search, so one invalidation drops the subtree', () => {
    const parent = searchKey('7')
    expect(searchResultsKey('7', '-bytes').slice(0, parent.length)).toEqual([...parent])
    expect(sessionFlowKey('7', 500).slice(0, sessionKey('7').length)).toEqual([...sessionKey('7')])
  })

  it('gives every top-level resource its own namespace', () => {
    const heads = [
      sensorsKey()[0],
      fieldsKey()[0],
      columnsKey()[0],
      enumKey('protocol')[0],
      estimateKey('from=a&to=b')[0],
      searchKey('7')[0],
      sessionKey('7')[0],
      protocolSchemaKey('dns')[0],
    ]
    expect(new Set(heads).size).toBe(heads.length)
  })

  it('treats the cursor as opaque', () => {
    const cursor = 'eyJ0cyI6MTIzfQ=='
    expect(searchResultsKey('7', cursor)).toContain(cursor)
  })
})
