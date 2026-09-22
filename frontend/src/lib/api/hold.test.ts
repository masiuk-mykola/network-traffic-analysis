import { describe, expect, it, vi } from 'vitest'

import { holdRead } from './hold'

describe('holdRead', () => {
  it('reads once and hands the same answer back inside the window', async () => {
    const read = vi.fn(async () => 'first')

    expect(await holdRead('a', 1_000, read)).toBe('first')
    expect(await holdRead('a', 1_000, read)).toBe('first')
    expect(read).toHaveBeenCalledOnce()
  })

  it('shares the read in flight, so two callers at once make one request', async () => {
    let release: (value: string) => void = () => {}
    const read = vi.fn(() => new Promise<string>((resolve) => (release = resolve)))

    const both = Promise.all([holdRead('b', 1_000, read), holdRead('b', 1_000, read)])
    release('shared')

    expect(await both).toEqual(['shared', 'shared'])
    expect(read).toHaveBeenCalledOnce()
  })

  it('reads again once the window has passed', async () => {
    const read = vi.fn(async () => Date.now())

    await holdRead('c', 0, read)
    await holdRead('c', 0, read)

    expect(read).toHaveBeenCalledTimes(2)
  })

  it('keeps nothing when the read fails, so the next caller tries again', async () => {
    const read = vi.fn(async () => {
      throw new Error('refused')
    })

    await expect(holdRead('d', 1_000, read)).rejects.toThrow('refused')
    await expect(holdRead('d', 1_000, read)).rejects.toThrow('refused')
    expect(read).toHaveBeenCalledTimes(2)
  })

  it('holds each key on its own', async () => {
    expect(await holdRead('e', 1_000, async () => 'e')).toBe('e')
    expect(await holdRead('f', 1_000, async () => 'f')).toBe('f')
  })
})
