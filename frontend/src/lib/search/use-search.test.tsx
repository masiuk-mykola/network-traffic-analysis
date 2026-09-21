import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MAX_POLL_MS } from './poll-interval'
import { isExpired } from './search-state'
import { useSearch } from './use-search'

const RUNNING = {
  id: 'srch-1',
  state: 'running',
  sensor_ids: ['hq-core'],
  from: '2025-10-27T06:00:00.000Z',
  to: '2025-10-27T12:00:00.000Z',
  filter: { all: [] },
  sort: '-ts',
  created_at: '2025-10-27T12:00:00.000Z',
  progress: { percent: 10 },
  stats: { matched_bytes_up: 0, matched_bytes_down: 0 },
  warnings: [],
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function stubFetch(bodies: () => Promise<Response>) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      calls.push(String(input))
      return bodies()
    }),
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useSearch', () => {
  it('asks nothing when no search has been started', () => {
    const calls = stubFetch(async () => Response.json(RUNNING, { status: 200 }))

    renderHook(() => useSearch(null), { wrapper })

    expect(calls).toEqual([])
  })

  it('keeps asking while the job runs, and waits longer each time', async () => {
    vi.useFakeTimers()
    const calls = stubFetch(async () => Response.json(RUNNING, { status: 200 }))

    renderHook(() => useSearch('srch-1'), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    expect(calls).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(500)
    expect(calls).toHaveLength(2)

    // The next one is a second away, not another half second.
    await vi.advanceTimersByTimeAsync(500)
    expect(calls).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(500)
    expect(calls).toHaveLength(3)
  })

  it('stops asking once the job has ended', async () => {
    vi.useFakeTimers()
    let answered = 0
    const calls = stubFetch(async () => {
      answered += 1
      return Response.json(answered === 1 ? RUNNING : { ...RUNNING, state: 'done' }, {
        status: 200,
      })
    })

    renderHook(() => useSearch('srch-1'), { wrapper })
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(500)
    expect(calls).toHaveLength(2)

    await vi.advanceTimersByTimeAsync(MAX_POLL_MS * 4)

    expect(calls).toHaveLength(2)
  })

  it('treats a discarded job as an ending rather than a failure', async () => {
    stubFetch(async () =>
      Response.json({ code: 'search_expired', detail: 'gone' }, { status: 410 }),
    )

    const { result } = renderHook(() => useSearch('srch-1'), { wrapper })

    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(isExpired(result.current.data!)).toBe(true)
    expect(result.current.isError).toBe(false)
  })
})
