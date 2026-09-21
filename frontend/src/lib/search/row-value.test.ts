import { describe, expect, it } from 'vitest'

import type { components } from '@api/schema'

import { rowValue } from './row-value'

type SessionRow = components['schemas']['SessionRow']

const ROW = {
  id: '72057639335362590',
  sensor_id: 'hq-core',
  start: '2025-10-27T11:59:54.117Z',
  end: '2025-10-27T11:59:55.193Z',
  duration_ms: 1076,
  protocol: 'tls',
  transport: 'tcp',
  src: { ip: '10.20.2.25', port: 37065, host: 'mx1.quillmere.example' },
  dst: { ip: '192.0.2.104', port: 443, host: 'weather.example.net', country: 'AT' },
  bytes: { up: 12019, down: 8044 },
  packets: { up: 14, down: 11 },
  risk: { score: 10, band: 'low', reasons: [] },
  summary: 'TLS1.3 weather.example.net',
  decoder: 'tls/2',
  files_count: 0,
  pcap_available: true,
} as unknown as SessionRow

const column = (key: string, type: string) => ({ key, type })

describe('rowValue', () => {
  it('renders the columns the server marks visible', () => {
    expect(rowValue(ROW, column('start', 'ts'))).toBe('2025-10-27 11:59:54.117 UTC')
    expect(rowValue(ROW, column('sensor', 'sensor'))).toBe('hq-core')
    expect(rowValue(ROW, column('src', 'ip_port'))).toBe('10.20.2.25:37065')
    expect(rowValue(ROW, column('dst', 'ip_port'))).toBe('192.0.2.104:443')
    expect(rowValue(ROW, column('protocol', 'protocol'))).toBe('tls')
    expect(rowValue(ROW, column('summary', 'text'))).toBe('TLS1.3 weather.example.net')
    expect(rowValue(ROW, column('bytes', 'bytes'))).toBe('20.1 kB')
    expect(rowValue(ROW, column('duration', 'duration'))).toBe('1.1 s')
    expect(rowValue(ROW, column('risk', 'risk'))).toBe('10 (low)')
  })

  it('renders the ones it publishes but hides by default', () => {
    expect(rowValue(ROW, column('id', 'id'))).toBe('72057639335362590')
    expect(rowValue(ROW, column('packets', 'text'))).toBe('25')
    expect(rowValue(ROW, column('decoder', 'text'))).toBe('tls/2')
    expect(rowValue(ROW, column('files', 'text'))).toBe('0')
  })

  it('renders a type this server publishes but never documented, as text', () => {
    // `dst_country` arrives as `geo_hint`, which is not in the documented list of column types.
    expect(rowValue(ROW, column('dst_country', 'geo_hint'))).toBe('AT')
  })

  it('marks a value the row does not carry', () => {
    const noCountry = { ...ROW, dst: { ip: '10.0.0.9', port: 53 } } as unknown as SessionRow

    expect(rowValue(noCountry, column('dst_country', 'geo_hint'))).toBe('—')
  })

  it('does not break on a column key it has never seen', () => {
    expect(rowValue(ROW, column('something_new', 'text'))).toBe('—')
  })
})
