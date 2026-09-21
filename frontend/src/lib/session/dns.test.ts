import { describe, expect, it } from 'vitest'

import { readDnsExchange } from './dns'

const V2 = {
  dns: {
    transaction_id: 46419,
    query: { name: '49d5ef90.video.example.net', type: 'A', class: 'IN' },
    rcode: { code: 3, name: 'NXDOMAIN' },
    flags: { qr: true, aa: false, tc: false, rd: true, ra: true },
    answers: [],
    authority: [
      { name: 'video.example.net', type: 'SOA', ttl: 3600, data: 'ns1.video.example.net …' },
    ],
    additional: [],
  },
}

// The older decoder quotes numbers, names the code with a bare number, and gives a single record
// where the canonical one gives a list.
const V1 = {
  dns: {
    transaction_id: '56926',
    query: { name: 'c81e40ba.packages.example.net', type: 'A', class: 'IN' },
    rcode: '3',
    flags: { qr: true, rd: true, ra: true },
    answers: [],
    authority: { name: 'packages.example.net', type: 'SOA', ttl: '3600', data: 'ns1 …' },
    additional: [],
  },
}

describe('readDnsExchange', () => {
  it('reads the canonical shape', () => {
    const exchange = readDnsExchange(V2)!

    expect(exchange.query).toEqual({ name: '49d5ef90.video.example.net', type: 'A', class: 'IN' })
    expect(exchange.responseCode).toEqual({ code: 3, name: 'NXDOMAIN' })
    expect(exchange.transactionId).toBe('46419')
    expect(exchange.authority[0]).toMatchObject({ type: 'SOA', ttl: 3600 })
  })

  it('names a response code that arrived as a bare number', () => {
    expect(readDnsExchange(V1)!.responseCode).toEqual({ code: 3, name: 'NXDOMAIN' })
  })

  it('keeps an unknown response code as the number it is', () => {
    const exchange = readDnsExchange({ dns: { rcode: 42 } })!

    expect(exchange.responseCode).toEqual({ code: 42, name: '42' })
  })

  it('says nothing about a response code that is not there', () => {
    expect(readDnsExchange({ dns: { query: { name: 'a.example' } } })!.responseCode).toEqual({
      code: null,
      name: '',
    })
  })

  it('wraps a single record into the list it belongs in', () => {
    const exchange = readDnsExchange(V1)!

    expect(exchange.authority).toHaveLength(1)
    expect(exchange.authority[0]).toMatchObject({ name: 'packages.example.net', type: 'SOA' })
  })

  it('reads a time to live the same whichever way it was quoted', () => {
    expect(readDnsExchange(V1)!.authority[0]?.ttl).toBe(readDnsExchange(V2)!.authority[0]?.ttl)
  })

  it('names the flags that are set, and only those', () => {
    expect(readDnsExchange(V2)!.flags).toEqual([
      'response',
      'recursion desired',
      'recursion available',
    ])
    expect(readDnsExchange(V1)!.flags).toEqual([
      'response',
      'recursion desired',
      'recursion available',
    ])
    expect(readDnsExchange({ dns: { flags: { qr: false, aa: true } } })!.flags).toEqual([
      'authoritative',
    ])
  })

  it('keeps the transaction id as the string it arrived as', () => {
    expect(readDnsExchange(V1)!.transactionId).toBe('56926')
  })

  it('is nothing at all when the payload holds no DNS', () => {
    expect(readDnsExchange({ tls: { sni: 'example.net' } })).toBeNull()
    expect(readDnsExchange({})).toBeNull()
    expect(readDnsExchange(null)).toBeNull()
  })
})
