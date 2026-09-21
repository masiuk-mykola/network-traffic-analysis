import { describe, expect, it } from 'vitest'

import type { components } from '@api/schema'

import { endingOf, EXPIRED, isFinished, isRunning, MISSING, progressOf } from './search-state'

type Search = components['schemas']['Search']

const job = (over: Record<string, unknown> = {}): Search =>
  ({
    id: 'srch-1',
    state: 'running',
    sensor_ids: ['hq-core'],
    from: '2025-10-27T06:00:00.000Z',
    to: '2025-10-27T12:00:00.000Z',
    filter: { all: [] },
    sort: '-ts',
    created_at: '2025-10-27T12:00:00.000Z',
    progress: {},
    stats: { matched_bytes_up: 0, matched_bytes_down: 0 },
    warnings: [],
    ...over,
  }) as unknown as Search

describe('isRunning / isFinished', () => {
  it('counts queued and running as still going', () => {
    expect(isRunning(job({ state: 'queued' }))).toBe(true)
    expect(isRunning(job({ state: 'running' }))).toBe(true)
  })

  it('counts every ending as finished', () => {
    for (const state of ['done', 'failed', 'cancelled']) {
      expect(isFinished(job({ state }))).toBe(true)
      expect(isRunning(job({ state }))).toBe(false)
    }
  })

  it('counts a discarded job as finished, and never as running', () => {
    expect(isFinished(EXPIRED)).toBe(true)
    expect(isRunning(EXPIRED)).toBe(false)
  })
})

describe('a job the server does not have', () => {
  it('is an ending of its own, not a failure and not an expiry', () => {
    expect(isRunning(MISSING)).toBe(false)
    expect(isFinished(MISSING)).toBe(true)
    expect(endingOf(MISSING)?.kind).toBe('missing')
    expect(endingOf(MISSING)?.detail).toMatch(/run it again/i)
    expect(progressOf(MISSING).percent).toBe(0)
  })
})

describe('endingOf', () => {
  it('has nothing to report while the job runs', () => {
    expect(endingOf(job({ state: 'running' }))).toBeNull()
  })

  it('reports each ending in its own terms', () => {
    expect(endingOf(job({ state: 'done' }))?.kind).toBe('done')
    expect(endingOf(job({ state: 'cancelled' }))?.kind).toBe('cancelled')
    expect(endingOf(job({ state: 'failed' }))?.kind).toBe('failed')
  })

  it('carries the reason the server gave for a failure', () => {
    const ending = endingOf(job({ state: 'failed', error: { detail: 'decoder exploded' } }))

    expect(ending?.detail).toBe('decoder exploded')
  })

  it('treats a discarded job as its own ending, not a failure', () => {
    const ending = endingOf(EXPIRED)

    expect(ending?.kind).toBe('expired')
    expect(ending?.detail).toMatch(/run it again/i)
  })
})

describe('progressOf', () => {
  it('reads what the server reported', () => {
    const shown = progressOf(
      job({
        progress: {
          percent: 42.5,
          scanned_sessions: 4200,
          total_sessions_estimate: 10_000,
          matched: 17,
          matched_is_estimate: false,
        },
      }),
    )

    expect(shown).toEqual({
      percent: 42.5,
      scanned: 4200,
      total: 10_000,
      matched: 17,
      matchedIsEstimate: false,
    })
  })

  it('survives a report with nothing filled in yet', () => {
    expect(progressOf(job({ progress: {} }))).toEqual({
      percent: 0,
      scanned: 0,
      total: null,
      matched: null,
      matchedIsEstimate: false,
    })
  })

  it('keeps the flag that says the match count is itself an estimate', () => {
    const shown = progressOf(job({ progress: { matched: 900, matched_is_estimate: true } }))

    expect(shown.matchedIsEstimate).toBe(true)
  })

  it('has nothing to show for a discarded job', () => {
    expect(progressOf(EXPIRED).percent).toBe(0)
  })
})
