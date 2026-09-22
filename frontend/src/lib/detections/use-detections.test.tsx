import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useDetections } from './use-detections'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const detection = (seq: number) => ({
  seq,
  id: `d${seq}`,
  ts: '2025-10-27T09:14:03.120Z',
  rule_id: 'r1',
  rule: 'Beaconing',
  severity: 'high',
  mitre: { technique_id: 'T1071', name: 'Application Layer Protocol' },
  sensor_id: 'hq-core',
  session_id: '72075232438042624',
  src: { ip: '10.0.0.1', port: 1 },
  dst: { ip: '10.0.0.2', port: 2 },
  summary: 'x',
})

/** A stand-in for the browser's own reader, which jsdom does not provide. */
class FakeEventSource {
  static last: FakeEventSource | null = null
  readonly closed: () => boolean
  private listeners = new Map<string, (event: MessageEvent) => void>()
  onerror: (() => void) | null = null
  private isClosed = false

  constructor(readonly url: string) {
    FakeEventSource.last = this
    this.closed = () => this.isClosed
  }

  addEventListener(name: string, handler: (event: MessageEvent) => void) {
    this.listeners.set(name, handler)
  }

  close() {
    this.isClosed = true
  }

  emit(name: string, data: unknown) {
    this.listeners.get(name)?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  emitRaw(name: string, data: unknown) {
    this.listeners.get(name)?.({ data } as MessageEvent)
  }
}

function stub(items: unknown[], status = 200) {
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      status === 200
        ? Response.json({ items, last_seq: items.length })
        : Response.json({ code: 'unavailable', detail: 'busy' }, { status }),
    ),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  FakeEventSource.last = null
})

describe('useDetections', () => {
  it('shows what the server already held, newest first', async () => {
    stub([detection(1), detection(2)])

    const { result } = renderHook(() => useDetections(), { wrapper })

    await waitFor(() => expect(result.current.detections).toHaveLength(2))
    expect(result.current.detections[0]?.seq).toBe(2)
  })

  it('reads the feed through our own server, never the API', async () => {
    stub([])

    renderHook(() => useDetections(), { wrapper })

    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())
    expect(FakeEventSource.last?.url).toBe('/api/detections/stream')
  })

  it('adds what arrives while watching', async () => {
    stub([detection(1)])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(result.current.detections).toHaveLength(1))

    FakeEventSource.last?.emit('detection', detection(7))

    await waitFor(() => expect(result.current.detections).toHaveLength(2))
    expect(result.current.detections[0]?.seq).toBe(7)
  })

  it('shows a detection once when the ring replays it', async () => {
    stub([detection(1)])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(result.current.detections).toHaveLength(1))

    FakeEventSource.last?.emit('detection', detection(1))
    FakeEventSource.last?.emit('detection', detection(2))

    await waitFor(() => expect(result.current.detections).toHaveLength(2))
  })

  it('follows what the connection says it is doing', async () => {
    stub([])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last?.emit('status', { status: 'live' })
    await waitFor(() => expect(result.current.status).toBe('live'))

    FakeEventSource.last?.emit('status', { status: 'stopped' })
    await waitFor(() => expect(result.current.status).toBe('stopped'))
  })

  it('reports a restart, so a gap is explained rather than silent', async () => {
    stub([])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last?.emit('reset', { oldest_seq: 900, last_seq: 1900 })

    await waitFor(() => expect(result.current.restarted).toBe(true))
  })

  it('says the connection is reconnecting when the reader errors', async () => {
    stub([])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last?.emit('status', { status: 'live' })
    await waitFor(() => expect(result.current.status).toBe('live'))
    FakeEventSource.last?.onerror?.()

    await waitFor(() => expect(result.current.status).toBe('reconnecting'))
  })

  it('ignores a frame whose body is not what it claims', async () => {
    stub([])
    const { result } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    FakeEventSource.last?.emitRaw('detection', 'not json')
    FakeEventSource.last?.emitRaw('status', undefined)

    expect(result.current.detections).toHaveLength(0)
    expect(result.current.status).toBe('reconnecting')
  })

  it('reports a refused seed, with a way to ask again', async () => {
    stub([], 503)

    const { result } = renderHook(() => useDetections(), { wrapper })

    await waitFor(() => expect(result.current.seed.error).toBeTruthy())
    expect(result.current.seed.isPending).toBe(false)
    expect(typeof result.current.seed.refetch).toBe('function')
  })

  it('closes the connection when the screen goes away', async () => {
    stub([])
    const { unmount } = renderHook(() => useDetections(), { wrapper })
    await waitFor(() => expect(FakeEventSource.last).not.toBeNull())

    const source = FakeEventSource.last
    unmount()

    expect(source?.closed()).toBe(true)
  })
})
