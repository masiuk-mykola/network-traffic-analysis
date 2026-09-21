import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { isNotFound } from './session-state'
import { useSession } from './use-session'

const HUGE_ID = '216172827537047572'

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
})

describe('useSession', () => {
  it('asks for the id exactly as it arrived, never as a number', async () => {
    const urls = stubFetch(async () => Response.json({ id: HUGE_ID }, { status: 200 }))

    const { result } = renderHook(() => useSession(HUGE_ID), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(urls[0]).toContain(HUGE_ID)
    expect(result.current.data).toMatchObject({ id: HUGE_ID })
  })

  it('treats a session the server does not have as an answer, not a failure', async () => {
    stubFetch(async () =>
      Response.json({ code: 'session_not_found', detail: 'no' }, { status: 404 }),
    )

    const { result } = renderHook(() => useSession('7'), { wrapper })

    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(isNotFound(result.current.data!)).toBe(true)
    expect(result.current.isError).toBe(false)
  })

  it('still reports any other failure', async () => {
    stubFetch(async () => Response.json({ code: 'upstream', detail: 'no' }, { status: 503 }))

    const { result } = renderHook(() => useSession('7'), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('asks for nothing when the page already read it', async () => {
    const urls = stubFetch(async () => Response.json({ id: '7' }, { status: 200 }))
    const status = { id: '7' } as never

    const { result } = renderHook(() => useSession('7', { sessionId: '7', status }), { wrapper })

    expect(result.current.data).toBe(status)
    expect(urls).toEqual([])
  })
})
