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

/** A stub that answers by cursor rather than by call order, so a poll can be told from a page. */
function routeFetch(answer: (cursor: string | null, call: number) => Record<string, unknown>) {
  const cursors: Array<string | null> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const cursor = new URL(String(input), 'http://x').searchParams.get('cursor')
      cursors.push(cursor)
      return Response.json(answer(cursor, cursors.length), { status: 200 })
    }),
  )
  return cursors
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

  it('waits out a delay the server named before reading the tail again', async () => {
    // The tail has its own address, so it has its own window: a 503 on the results read silences
    // the results read, and the poll's own cadence knows nothing about it.
    vi.useFakeTimers()
    const urls: string[] = []
    let first = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input))
        if (first) {
          first = false
          return Response.json(page({ next_cursor: null, complete: false }), { status: 200 })
        }
        return Response.json(
          { code: 'unavailable', detail: 'busy' },
          { status: 503, headers: { 'retry-after': '4', 'content-type': 'application/json' } },
        )
      }),
    )

    renderHook(() => useResults('srch-1', true), { wrapper })

    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(1_000)
    const refusedAt = urls.length
    expect(refusedAt).toBeGreaterThan(1)

    // The cadence alone would have asked again a second from now; the server asked for four.
    await vi.advanceTimersByTimeAsync(2_000)
    expect(urls).toHaveLength(refusedAt)

    await vi.advanceTimersByTimeAsync(2_500)
    expect(urls.length).toBeGreaterThan(refusedAt)
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
  it('polls the page the job is still filling, not the pages already read', async () => {
    // A search appends its matches and a cursor is a position in them, so every page but the last
    // is settled. Re-reading them would be the same answer bought again, on every tick.
    vi.useFakeTimers()
    const cursors = routeFetch((cursor) =>
      cursor === 'c1'
        ? page({ items: [{ id: 'b' }], next_cursor: null, complete: false })
        : page({ items: [{ id: 'a' }], next_cursor: 'c1', complete: false }),
    )

    const { result } = renderHook(() => useResults('srch-1', true), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    await result.current.fetchNextPage()
    await vi.advanceTimersByTimeAsync(0)

    const loaded = cursors.length
    await vi.advanceTimersByTimeAsync(6_000)

    const polled = cursors.slice(loaded)
    expect(polled.length).toBeGreaterThan(0)
    expect(polled).not.toContain(null)
    expect(new Set(polled)).toEqual(new Set(['c1']))
  })

  it('shows rows that arrive on a later poll, without repeating the ones already held', async () => {
    vi.useFakeTimers()
    routeFetch((_cursor, call) =>
      call === 1
        ? page({ items: [{ id: 'a' }], next_cursor: null, complete: false })
        : page({ items: [{ id: 'a' }, { id: 'b' }], next_cursor: null, complete: false }),
    )

    const { result } = renderHook(() => useResults('srch-1', true), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    expect(rowsOf(result.current)).toEqual(['a'])

    await vi.advanceTimersByTimeAsync(2_000)

    expect(rowsOf(result.current)).toEqual(['a', 'b'])
  })

  it('stops asking once the search says it is complete', async () => {
    vi.useFakeTimers()
    const cursors = routeFetch((_cursor, call) =>
      call === 1
        ? page({ items: [{ id: 'a' }], next_cursor: null, complete: false })
        : page({ items: [{ id: 'a' }, { id: 'b' }], next_cursor: null, complete: true }),
    )

    const { result } = renderHook(() => useResults('srch-1', true), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(2_000)

    expect(result.current.data?.pages.at(-1)?.complete).toBe(true)
    const afterComplete = cursors.length

    await vi.advanceTimersByTimeAsync(30_000)

    expect(cursors).toHaveLength(afterComplete)
    expect(rowsOf(result.current)).toEqual(['a', 'b'])
  })

  it('does not read the tail twice for one answer it already has', async () => {
    // Becoming the tail must not repeat the read that produced the page it stands for.
    vi.useFakeTimers()
    const cursors = routeFetch(() => page({ next_cursor: null, complete: false }))

    renderHook(() => useResults('srch-1', true), { wrapper })
    await vi.advanceTimersByTimeAsync(0)

    expect(cursors).toHaveLength(1)
  })

  it('reports a refused tail read where the rows are, and retries that read alone', async () => {
    vi.useFakeTimers()
    const urls: string[] = []
    let refuse = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input))
        if (refuse) {
          return Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 })
        }
        return Response.json(page({ next_cursor: null, complete: false }), { status: 200 })
      }),
    )

    const { result } = renderHook(() => useResults('srch-1', true), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    expect(result.current.isError).toBe(false)

    refuse = true
    await vi.advanceTimersByTimeAsync(2_000)

    // The rows the table already holds stay; the failure is reported beside them.
    expect(result.current.isError).toBe(true)
    expect(rowsOf(result.current)).toEqual(['1'])

    refuse = false
    const before = urls.length
    result.current.retry()
    await vi.advanceTimersByTimeAsync(0)

    expect(urls.length).toBeGreaterThan(before)
    await vi.advanceTimersByTimeAsync(0)
    expect(result.current.isError).toBe(false)
  })
})

function rowsOf(results: { data?: { pages: Array<{ items: Array<{ id: string }> }> } }) {
  return results.data?.pages.flatMap((entry) => entry.items.map((item) => item.id)) ?? []
}
