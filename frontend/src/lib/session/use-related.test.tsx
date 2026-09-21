import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { RelatedWindow } from './related'
import { useRelated } from './use-related'

const ROW = { id: '7', summary: 'one' }

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client()}>{children}</QueryClientProvider>
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

const page = (over: Record<string, unknown> = {}) => ({ items: [ROW], next_cursor: null, ...over })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useRelated', () => {
  it('asks within the window it was given', async () => {
    const urls = stubFetch([page()])

    const { result } = renderHook(() => useRelated('7', '6h'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls[0]).toContain('window=6h')
    expect(urls[0]).not.toContain('cursor=')
  })

  it('sends the marker back exactly as it arrived', async () => {
    const cursor = 'eyJ0cyI6MX0=:offset/3+4'
    const urls = stubFetch([page({ next_cursor: cursor }), page()])

    const { result } = renderHook(() => useRelated('7', '1h'), { wrapper })
    await waitFor(() => expect(result.current.hasNextPage).toBe(true))
    await result.current.fetchNextPage()

    await waitFor(() => expect(urls).toHaveLength(2))
    expect(urls[1]).toContain(`cursor=${encodeURIComponent(cursor)}`)
    expect(urls[1]).toContain('window=1h')
  })

  it('has no next page when the server offers none', async () => {
    stubFetch([page()])

    const { result } = renderHook(() => useRelated('7', '1h'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.hasNextPage).toBe(false)
  })

  it('reads each window once, and a window already read not at all', async () => {
    const urls = stubFetch([page()])
    const shared = client()
    const provider = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={shared}>{children}</QueryClientProvider>
    )

    const { result, rerender } = renderHook(({ window }) => useRelated('7', window), {
      wrapper: provider,
      initialProps: { window: '1h' as RelatedWindow },
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    rerender({ window: '6h' })
    await waitFor(() => expect(urls).toHaveLength(2))

    rerender({ window: '1h' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls).toHaveLength(2)
  })
})
