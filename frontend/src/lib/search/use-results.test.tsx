import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PAGE_SIZE, useResults } from './use-results'

const ROW = { id: '1', summary: 'one' }

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function stubFetch(pages: Array<Record<string, unknown>>) {
  const urls: string[] = []
  let index = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input))
      const page = pages[Math.min(index, pages.length - 1)]
      index += 1
      return Response.json(page, { status: 200 })
    }),
  )
  return urls
}

const page = (over: Record<string, unknown> = {}) => ({
  items: [ROW],
  next_cursor: null,
  complete: true,
  matched_so_far: 1,
  ...over,
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useResults', () => {
  it('asks for nothing without a search', () => {
    const urls = stubFetch([page()])

    renderHook(() => useResults(null, false), { wrapper })

    expect(urls).toEqual([])
  })

  it('asks for no more rows than the server accepts', async () => {
    const urls = stubFetch([page()])

    const { result } = renderHook(() => useResults('srch-1', false), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls[0]).toContain(`limit=${PAGE_SIZE}`)
    expect(PAGE_SIZE).toBe(500)
  })

  it('sends the cursor back exactly as it arrived', async () => {
    const cursor = 'eyJ0cyI6MTIzfQ==:offset/7+8'
    const urls = stubFetch([page({ next_cursor: cursor, complete: false }), page()])

    const { result } = renderHook(() => useResults('srch-1', false), { wrapper })
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await result.current.fetchNextPage()

    await waitFor(() => expect(urls).toHaveLength(2))
    expect(urls[1]).toContain(`cursor=${encodeURIComponent(cursor)}`)
  })

  it('treats a caught-up page as no next page', async () => {
    stubFetch([page({ next_cursor: null, complete: false })])

    const { result } = renderHook(() => useResults('srch-1', true), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.hasNextPage).toBe(false)
  })

  it('reads the tail while the job runs, and stops once it does not', async () => {
    vi.useFakeTimers()
    const urls = stubFetch([page({ next_cursor: null, complete: false })])

    const { rerender } = renderHook(({ running }) => useResults('srch-1', running), {
      wrapper,
      initialProps: { running: true },
    })

    await vi.advanceTimersByTimeAsync(0)
    expect(urls).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(urls.length).toBeGreaterThan(1)

    const afterRunning = urls.length
    rerender({ running: false })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(urls).toHaveLength(afterRunning)
  })
})
