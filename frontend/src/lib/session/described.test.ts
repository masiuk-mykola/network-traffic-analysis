import { describe, expect, it } from 'vitest'

import { splitDecoded } from './described'

const FIELDS = [
  { path: 'dns.query.name', title: 'Query name', type: 'string' },
  { path: 'dns.rcode.code', title: 'Response code', type: 'number' },
  { path: 'dns.answers[].data', title: 'Answer', type: 'ip' },
  { path: 'dns.user', title: 'User', type: 'string', sensitive: true },
]

const V2 = {
  dns: {
    query: { name: 'prn-16.quillmere.example', type: 'A' },
    rcode: { code: 0, name: 'NOERROR' },
    answers: [{ data: '10.20.0.7' }, { data: '10.20.0.8' }],
  },
}

const V1 = { dns: { rcode: '2', authority: { name: 'example.org' } } }

describe('splitDecoded', () => {
  it('keeps the published order and titles, with every occurrence of a repeated field', () => {
    const { described } = splitDecoded(V2, FIELDS)

    expect(described.map((row) => row.title)).toEqual(['Query name', 'Response code', 'Answer'])
    expect(described[2]?.values).toEqual(['10.20.0.7', '10.20.0.8'])
  })

  it('leaves out a described field this session does not carry', () => {
    const { described } = splitDecoded(V2, FIELDS)

    expect(described.some((row) => row.title === 'User')).toBe(false)
  })

  it('shows what the description did not claim, under its own path', () => {
    const { undescribed } = splitDecoded(V2, FIELDS)

    expect(undescribed.map((row) => row.path)).toEqual(['dns.query.type', 'dns.rcode.name'])
  })

  it('puts an older decoder’s differently shaped values in the undescribed block', () => {
    const { described, undescribed } = splitDecoded(V1, FIELDS)

    expect(described).toEqual([])
    expect(undescribed).toEqual([
      { path: 'dns.rcode', value: '2' },
      { path: 'dns.authority.name', value: 'example.org' },
    ])
  })

  it('carries the sensitive marking through', () => {
    const { described } = splitDecoded({ dns: { user: 'jarek' } }, FIELDS)

    expect(described[0]).toMatchObject({ title: 'User', sensitive: true })
  })

  it('says nothing about a session with nothing decoded', () => {
    expect(splitDecoded({}, FIELDS)).toEqual({ described: [], undescribed: [] })
  })
})
