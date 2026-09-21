import { describe, expect, it } from 'vitest'

import { EMPTY } from './empty'
import { formatEndpoint } from './endpoint'

describe('formatEndpoint', () => {
  it('puts the address and port together', () => {
    expect(formatEndpoint({ ip: '10.12.3.4', port: 443 }).address).toBe('10.12.3.4:443')
  })

  it('brackets an IPv6 address so the port is readable', () => {
    expect(formatEndpoint({ ip: '2001:db8::1', port: 53 }).address).toBe('[2001:db8::1]:53')
  })

  it('leaves out what the API did not send, rather than an empty gap', () => {
    const shown = formatEndpoint({ ip: '10.12.3.4', port: 443 })

    expect(shown.host).toBeNull()
    expect(shown.country).toBeNull()
  })

  it('passes through the hostname and country when they are there', () => {
    const shown = formatEndpoint({
      ip: '93.184.216.34',
      port: 443,
      host: 'example.com',
      country: 'US',
    })

    expect(shown.host).toBe('example.com')
    expect(shown.country).toBe('US')
  })

  it('survives a missing endpoint', () => {
    expect(formatEndpoint(null).address).toBe(EMPTY)
  })
})
