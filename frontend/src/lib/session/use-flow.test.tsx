import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useFlow } from './use-flow'

const FLOW = { session_id: '7', bucket_ms: 1_000, samples: [] }

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function stubFetch() {
  const urls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input))
      return Response.json(FLOW, { status: 200 })
    }),
  )
  return urls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useFlow', () => {
  it('asks for nothing until a width is chosen', () => {
    const urls = stubFetch()

    renderHook(() => useFlow('7', null), { wrapper })

    expect(urls).toEqual([])
  })

  it('sends the width it was given', async () => {
    const urls = stubFetch()

    const { result } = renderHook(() => useFlow('7', 5_000), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls[0]).toContain('bucket_ms=5000')
  })

  it('reads one width once, however many times it is rendered', async () => {
    const urls = stubFetch()

    const { result, rerender } = renderHook(() => useFlow('7', 1_000), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    rerender()
    rerender()

    expect(urls).toHaveLength(1)
  })

  it('treats two widths as two separate answers', async () => {
    const urls = stubFetch()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const shared = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )

    const { result, rerender } = renderHook(({ width }) => useFlow('7', width), {
      wrapper: shared,
      initialProps: { width: 1_000 },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    rerender({ width: 5_000 })
    await waitFor(() => expect(urls).toHaveLength(2))

    // Going back to a width already read costs nothing.
    rerender({ width: 1_000 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls).toHaveLength(2)
  })
})
