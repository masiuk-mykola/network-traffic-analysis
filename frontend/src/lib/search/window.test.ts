import { describe, expect, it } from 'vitest'

import { defaultWindow, WINDOW_HOURS, WINDOW_PRESETS } from './window'

const sensor = (id: string, lastPacketAt: string | undefined) => ({
  id,
  last_packet_at: lastPacketAt,
})

describe('defaultWindow', () => {
  it('ends at the latest traffic anyone reported, not at the clock', () => {
    const window = defaultWindow([
      sensor('hq-core', '2025-10-27T12:32:14.963Z'),
      sensor('dc-east', '2025-10-27T12:30:00.000Z'),
    ])

    expect(window?.to).toBe('2025-10-27T12:32:14.963Z')
  })

  it('opens a fixed span before that', () => {
    const window = defaultWindow([sensor('hq-core', '2025-10-27T12:00:00.000Z')])

    expect(window?.from).toBe('2025-10-27T06:00:00.000Z')
    expect(WINDOW_HOURS).toBe(6)
  })

  it('is not dragged back by a point that is behind', () => {
    const window = defaultWindow([
      sensor('hq-core', '2025-10-27T12:32:14.963Z'),
      sensor('harbor-branch', '2025-10-27T12:27:26.238Z'),
    ])

    expect(window?.to).toBe('2025-10-27T12:32:14.963Z')
  })

  it('says nothing rather than inventing a window', () => {
    expect(defaultWindow([])).toBeNull()
    expect(defaultWindow([sensor('hq-core', undefined)])).toBeNull()
    expect(defaultWindow([sensor('hq-core', 'not a time')])).toBeNull()
  })

  it('ignores one unreadable timestamp among good ones', () => {
    const window = defaultWindow([
      sensor('hq-core', 'not a time'),
      sensor('dc-east', '2025-10-27T09:00:00.000Z'),
    ])

    expect(window?.to).toBe('2025-10-27T09:00:00.000Z')
  })

  it('opens a span of the asked length before the same end', () => {
    const sensors = [sensor('hq-core', '2025-10-27T12:00:00.000Z')]

    expect(defaultWindow(sensors, 1)).toEqual({
      from: '2025-10-27T11:00:00.000Z',
      to: '2025-10-27T12:00:00.000Z',
    })
    expect(defaultWindow(sensors, 24)?.from).toBe('2025-10-26T12:00:00.000Z')
  })

  it('offers the default span among its presets', () => {
    expect(WINDOW_PRESETS).toContain(WINDOW_HOURS)
  })

  it('opens a span of the asked length before the same end', () => {
    const sensors = [sensor('hq-core', '2025-10-27T12:00:00.000Z')]

    expect(defaultWindow(sensors, 1)).toEqual({
      from: '2025-10-27T11:00:00.000Z',
      to: '2025-10-27T12:00:00.000Z',
    })
    expect(defaultWindow(sensors, 24)?.from).toBe('2025-10-26T12:00:00.000Z')
  })

  it('offers the default span among its presets', () => {
    expect(WINDOW_PRESETS).toContain(WINDOW_HOURS)
  })
})
