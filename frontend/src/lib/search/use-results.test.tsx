import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SortKey } from './sort'
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

  it('asks for an order only once the job has finished', async () => {
    const running = stubFetch([page({ next_cursor: null, complete: false })])
    const { result: whileRunning } = renderHook(() => useResults('srch-1', true, '-bytes'), {
      wrapper,
    })
    await waitFor(() => expect(whileRunning.current.isSuccess).toBe(true))
    expect(running[0]).not.toContain('sort=')

    vi.unstubAllGlobals()
    const finished = stubFetch([page()])
    const { result } = renderHook(() => useResults('srch-1', false, '-bytes'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(finished[0]).toContain('sort=-bytes')
  })

  it('leaves the default order out of the request', async () => {
    const urls = stubFetch([page()])

    const { result } = renderHook(() => useResults('srch-1', false, '-ts'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls[0]).not.toContain('sort=')
  })

  it('starts a new order from the first page, carrying no cursor across', async () => {
    const cursor = 'cursor-from-the-other-order'
    const urls = stubFetch([page({ next_cursor: cursor, complete: false }), page()])

    const { result, rerender } = renderHook(({ sort }) => useResults('srch-1', false, sort), {
      wrapper,
      initialProps: { sort: '-ts' as SortKey },
    })
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))

    rerender({ sort: 'risk' })

    await waitFor(() => expect(urls).toHaveLength(2))
    expect(urls[1]).not.toContain('cursor=')
    expect(urls[1]).toContain('sort=risk')
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
