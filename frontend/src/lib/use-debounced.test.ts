import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useDebounced } from './use-debounced'

afterEach(() => {
  vi.useRealTimers()
})

describe('useDebounced', () => {
  it('holds the value until the changes stop', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 400), {
      initialProps: { value: 'a' },
    })

    rerender({ value: 'b' })
    rerender({ value: 'c' })
    expect(result.current).toBe('a')

    act(() => void vi.advanceTimersByTime(400))

    expect(result.current).toBe('c')
  })

  it('lets a single change through after the delay', () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ value }) => useDebounced(value, 400), {
      initialProps: { value: 1 },
    })

    rerender({ value: 2 })
    act(() => void vi.advanceTimersByTime(399))
    expect(result.current).toBe(1)

    act(() => void vi.advanceTimersByTime(1))
    expect(result.current).toBe(2)
  })

  it('starts with the value it was given', () => {
    const { result } = renderHook(() => useDebounced('now', 400))

    expect(result.current).toBe('now')
  })
})
