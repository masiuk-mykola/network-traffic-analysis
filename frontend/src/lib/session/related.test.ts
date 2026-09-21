import { describe, expect, it } from 'vitest'

import { describeRelated, RELATED_WINDOWS, type RelatedRow } from './related'

const row = (over: Partial<RelatedRow> = {}): RelatedRow =>
  ({
    id: '72057639299711033',
    sensor_id: 'hq-core',
    start: '2025-10-27T11:25:24.401Z',
    end: '2025-10-27T11:25:24.407Z',
    duration_ms: 6,
    protocol: 'tcp',
    transport: 'tcp',
    src: { ip: '10.20.9.250', port: 55425, host: 'scan-it-01.quillmere.example' },
    dst: { ip: '10.20.4.41', port: 139 },
    bytes: { up: 74, down: 54 },
    packets: { up: 1, down: 1 },
    risk: { score: 12, band: 'low', reasons: [] },
    summary: 'TCP 10.20.9.250:55425 → 10.20.4.41:139',
    decoder: 'tcp/2',
    files_count: 0,
    pcap_available: true,
    ...over,
  }) as RelatedRow

describe('RELATED_WINDOWS', () => {
  it('offers only the windows the server accepts', () => {
    expect(RELATED_WINDOWS.map((option) => option.value)).toEqual(['15m', '1h', '6h'])
  })
})

describe('describeRelated', () => {
  it('reads the parts of one line out of the row the server sent', () => {
    const line = describeRelated(row())

    expect(line.href).toBe('/sessions/72057639299711033')
    expect(line.when).toContain('2025-10-27')
    expect(line.protocol).toBe('tcp')
    expect(line.size).toBe('128 B')
    expect(line.risk).toBe('12 (low)')
  })

  it('names an endpoint by its host where the server gave one, and by its address otherwise', () => {
    const line = describeRelated(row())

    expect(line.from).toBe('scan-it-01.quillmere.example:55425')
    expect(line.to).toBe('10.20.4.41:139')
  })

  it('keeps an identifier as the string it arrived as', () => {
    const line = describeRelated(row({ id: '216172827537047572' }))

    expect(line.href).toBe('/sessions/216172827537047572')
  })

  it('shows a session that carried nothing as carrying nothing', () => {
    expect(describeRelated(row({ bytes: { up: 0, down: 0 } })).size).toBe('0 B')
  })
})
