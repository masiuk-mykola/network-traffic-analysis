import { describe, expect, it } from 'vitest'

import {
  bucketChoices,
  defaultBucket,
  MAX_BUCKET_MS,
  MIN_BUCKET_MS,
  toSeries,
  type FlowSample,
} from './flow'

const sample = (t: number, over: Partial<FlowSample> = {}): FlowSample => ({
  t,
  bytes_up: 1000,
  bytes_down: 100,
  packets_up: 10,
  packets_down: 2,
  ...over,
})

describe('bucketChoices', () => {
  it('offers only widths the server accepts', () => {
    for (const duration of [58, 1_000, 127_156, 3_600_000]) {
      for (const width of bucketChoices(duration)) {
        expect(width).toBeGreaterThanOrEqual(MIN_BUCKET_MS)
        expect(width).toBeLessThanOrEqual(MAX_BUCKET_MS)
      }
    }
  })

  it('offers different widths for a two-minute and a fifty-millisecond session', () => {
    expect(bucketChoices(127_156)).not.toEqual(bucketChoices(58))
  })

  it('has nothing to offer but the finest width for a session shorter than one bucket', () => {
    expect(bucketChoices(58)).toEqual([MIN_BUCKET_MS])
  })

  it('offers a handful at most, coarsest last', () => {
    const choices = bucketChoices(127_156)

    expect(choices.length).toBeGreaterThan(1)
    expect(choices.length).toBeLessThanOrEqual(4)
    expect([...choices].sort((a, b) => a - b)).toEqual(choices)
  })

  it('falls back to the coarsest width for a session longer than any ladder step', () => {
    expect(bucketChoices(6 * 60 * 60_000)).toEqual([MAX_BUCKET_MS])
  })
})

describe('defaultBucket', () => {
  it('is one of the offered widths', () => {
    for (const duration of [58, 2_000, 127_156, 3_600_000]) {
      expect(bucketChoices(duration)).toContain(defaultBucket(duration))
    }
  })

  it('is finer for a short session than for a long one', () => {
    expect(defaultBucket(2_000)).toBeLessThan(defaultBucket(3_600_000))
  })
})

describe('toSeries', () => {
  const samples = [sample(1_000), sample(2_000, { bytes_up: 4_000 }), sample(5_000)]

  it('places every column at its own moment, leaving the silence between them', () => {
    const series = toSeries(samples, 1_000, 'bytes')

    expect(series.columns.map((column) => column.t)).toEqual([1_000, 2_000, 5_000])
    // Two buckets of silence sit between the second column and the third: over a five-second span
    // that is two fifths of the picture, not zero.
    const [, second, third] = series.columns
    expect(third!.offset - (second!.offset + second!.width)).toBeCloseTo(0.4, 5)
  })

  it('scales both directions against one peak', () => {
    const series = toSeries(samples, 1_000, 'bytes')

    expect(series.peak).toBe(4_000)
    expect(series.totals).toEqual({ up: 6_000, down: 300 })
  })

  it('reads packets when asked for packets', () => {
    const series = toSeries(samples, 1_000, 'packets')

    expect(series.peak).toBe(10)
    expect(series.totals).toEqual({ up: 30, down: 6 })
  })

  it('spans a single sample without dividing by nothing', () => {
    const series = toSeries([sample(1_000)], 1_000, 'bytes')

    expect(series.columns).toHaveLength(1)
    expect(series.columns[0]?.offset).toBe(0)
    expect(series.columns[0]?.width).toBe(1)
  })

  it('has nothing to show for an empty series', () => {
    const series = toSeries([], 1_000, 'bytes')

    expect(series.columns).toEqual([])
    expect(series.peak).toBe(0)
    expect(series.totals).toEqual({ up: 0, down: 0 })
  })

  it('keeps the samples in time order whatever order they arrived in', () => {
    const series = toSeries([sample(5_000), sample(1_000)], 1_000, 'bytes')

    expect(series.columns.map((column) => column.t)).toEqual([1_000, 5_000])
  })
})
