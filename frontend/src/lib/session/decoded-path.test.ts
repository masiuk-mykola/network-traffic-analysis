import { describe, expect, it } from 'vitest'

import { entriesAt, leaves, valuesAt } from './decoded-path'

const V2 = {
  dns: {
    transaction_id: 59322,
    query: { name: 'prn-16.quillmere.example', type: 'A' },
    rcode: { code: 0, name: 'NOERROR' },
    answers: [
      { name: 'prn-16.quillmere.example', type: 'A', ttl: 3600 },
      { name: 'prn-16.quillmere.example', type: 'AAAA', ttl: 60 },
    ],
  },
}

// The older decoder puts a scalar where the description expects an object, and a single object
// where it expects a list.
const V1 = {
  dns: {
    rcode: '2',
    authority: { name: 'example.org', type: 'SOA' },
    answers: [],
  },
}

describe('valuesAt', () => {
  it('reads a nested value', () => {
    expect(valuesAt(V2, 'dns.query.name')).toEqual(['prn-16.quillmere.example'])
    expect(valuesAt(V2, 'dns.transaction_id')).toEqual([59322])
  })

  it('expands a list into one value per element', () => {
    expect(valuesAt(V2, 'dns.answers[].type')).toEqual(['A', 'AAAA'])
    expect(valuesAt(V2, 'dns.answers[].ttl')).toEqual([3600, 60])
  })

  it('finds nothing where the decoder put a scalar instead of an object', () => {
    expect(valuesAt(V1, 'dns.rcode.code')).toEqual([])
  })

  it('finds nothing where a list was expected and a single object arrived', () => {
    expect(valuesAt(V1, 'dns.authority[].name')).toEqual([])
  })

  it('finds nothing in an empty list, and nothing down a branch that is absent', () => {
    expect(valuesAt(V1, 'dns.answers[].name')).toEqual([])
    expect(valuesAt(V1, 'dns.query.name')).toEqual([])
    expect(valuesAt({}, 'dns.query.name')).toEqual([])
  })

  it('keeps a value that is there but empty, and drops one that is null', () => {
    expect(valuesAt({ tls: { sni: '' } }, 'tls.sni')).toEqual([''])
    expect(valuesAt({ tls: { sni: null } }, 'tls.sni')).toEqual([])
  })

  it('reads a list that is itself the value', () => {
    expect(valuesAt({ tcp: { flags_seen: ['SYN', 'ACK'] } }, 'tcp.flags_seen[]')).toEqual([
      'SYN',
      'ACK',
    ])
  })
})

describe('entriesAt', () => {
  it('names each value it found, with the element it came from', () => {
    expect(entriesAt(V2, 'dns.answers[].type')).toEqual([
      { path: 'dns.answers[0].type', value: 'A' },
      { path: 'dns.answers[1].type', value: 'AAAA' },
    ])
  })

  it('names a plain value by its own path', () => {
    expect(entriesAt(V2, 'dns.query.name')).toEqual([
      { path: 'dns.query.name', value: 'prn-16.quillmere.example' },
    ])
  })
})

describe('leaves', () => {
  it('names every value in the payload, lists included', () => {
    expect(leaves({ dns: { rcode: '2', answers: [{ ttl: 60 }] } })).toEqual([
      { path: 'dns.rcode', value: '2' },
      { path: 'dns.answers[0].ttl', value: 60 },
    ])
  })

  it('treats an empty list or object as nothing to show', () => {
    expect(leaves({ dns: { answers: [], flags: {} } })).toEqual([])
  })
})
