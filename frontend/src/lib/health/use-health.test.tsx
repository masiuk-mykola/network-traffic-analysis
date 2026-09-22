import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HEALTH_INTERVAL_MS, useHealth } from './use-health'

const OK = {
  status: 'ok',
  components: { index: { status: 'ok' }, decoder: { status: 'ok' } },
  server_time: '2025-10-27T12:00:00.000Z',
  version: '1.0.0',
}

const DEGRADED = {
  status: 'degraded',
  components: {
    index: { status: 'degraded', detail: 'The session index is rebuilding; searches may be slow.' },
    decoder: { status: 'ok' },
  },
  server_time: '2025-10-27T12:00:00.000Z',
  version: '1.0.0',
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function stubFetch(reply: () => Promise<Response>) {
  const urls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input))
      return reply()
    }),
  )
  return urls
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useHealth', () => {
  it('asks no more often than the server allows, and not in the background', () => {
    // The server grades the median gap between health reads at ten seconds.
    expect(HEALTH_INTERVAL_MS).toBeGreaterThanOrEqual(30_000)
  })

  it('says nothing while the server is well', async () => {
    stubFetch(async () => Response.json(OK))

    const { result } = renderHook(() => useHealth(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it('reports a degraded part in the server’s own words', async () => {
    stubFetch(async () => Response.json(DEGRADED))

    const { result } = renderHook(() => useHealth(), { wrapper })

    await waitFor(() => expect(result.current.data?.length).toBe(1))
    expect(result.current.data?.[0]).toEqual({
      name: 'index',
      detail: 'The session index is rebuilding; searches may be slow.',
    })
  })

  it('names a degraded part even when the server gives no sentence', async () => {
    stubFetch(async () =>
      Response.json({ ...DEGRADED, components: { pcap_store: { status: 'degraded' } } }),
    )

    const { result } = renderHook(() => useHealth(), { wrapper })

    await waitFor(() => expect(result.current.data?.length).toBe(1))
    expect(result.current.data?.[0]).toEqual({ name: 'pcap_store', detail: null })
  })

  it('stays silent when it cannot ask: how the server is, is not the reader’s problem', async () => {
    stubFetch(async () => Response.json({ code: 'unavailable' }, { status: 503 }))

    const { result } = renderHook(() => useHealth(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
  })

  it('reads it once however many screens ask', async () => {
    const urls = stubFetch(async () => Response.json(OK))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const shared = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => [useHealth(), useHealth()] as const, { wrapper: shared })

    await waitFor(() => expect(result.current[0].isSuccess).toBe(true))
    expect(urls).toHaveLength(1)
  })
})
