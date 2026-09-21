import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NOT_FOUND, type SessionStatus } from '@lib/session/session-state'

import { SessionView } from './session-view'

vi.mock('next/navigation', () => ({ useRouter: () => ({ back: vi.fn() }) }))

const DNS_SCHEMA = {
  protocol: 'dns',
  decoder_versions: ['v1', 'v2'],
  fields: [
    { path: 'dns.transaction_id', title: 'Transaction id', type: 'number' },
    { path: 'dns.query.name', title: 'Query name', type: 'string' },
    { path: 'dns.rcode.code', title: 'Response code', type: 'number' },
    { path: 'dns.answers[].data', title: 'Answer', type: 'ip' },
  ],
}

/** The real shape of a session, trimmed to what this screen reads. */
function session(over: Record<string, unknown> = {}): SessionStatus {
  return {
    id: '216172827537047572',
    sensor_id: 'harbor-branch',
    start: '2025-10-27T13:59:57.375Z',
    end: '2025-10-27T13:59:57.415Z',
    duration_ms: 40,
    protocol: 'dns',
    transport: 'udp',
    src: { ip: '10.20.4.158', port: 33787 },
    dst: { ip: '10.20.0.53', port: 53 },
    bytes: { up: 74, down: 271 },
    packets: { up: 1, down: 1 },
    risk: { score: 7, band: 'low', reasons: [] },
    summary: 'A blog.example.org',
    decoder: 'dns/1',
    files_count: 0,
    pcap_available: true,
    decoded: {},
    detections: [],
    files: [],
    pcap: { available: true },
    ...over,
  } as unknown as SessionStatus
}

const V2_DECODED = {
  dns: {
    transaction_id: 59322,
    query: { name: 'prn-16.quillmere.example', type: 'A' },
    rcode: { code: 0, name: 'NOERROR' },
    answers: [{ data: '10.20.0.7' }, { data: '10.20.0.8' }],
  },
}

// The older decoder: a scalar where the description expects an object, an object where it expects
// a list.
const V1_DECODED = {
  dns: {
    transaction_id: '6001',
    rcode: '2',
    authority: { name: 'example.org', type: 'SOA' },
  },
}

function renderView(initialStatus: SessionStatus) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes('meta/schema')) return Response.json(DNS_SCHEMA, { status: 200 })
      return Response.json({ code: 'unexpected' }, { status: 500 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SessionView sessionId="216172827537047572" initialStatus={initialStatus} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SessionView', () => {
  it('states what the session is', () => {
    renderView(session())

    const summary = screen.getByRole('region', { name: 'Session summary' })
    expect(summary).toHaveTextContent('harbor-branch')
    expect(summary).toHaveTextContent('dns over udp')
    expect(summary).toHaveTextContent('10.20.0.53:53')
    expect(summary).toHaveTextContent('345 B')
    expect(summary).toHaveTextContent('7 (low)')
  })

  it('shows the id exactly as the server gave it', () => {
    renderView(session())

    expect(screen.getByRole('region', { name: 'Session summary' })).toHaveTextContent(
      '216172827537047572',
    )
  })

  it('renders the transaction with the published labels, in the published order', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))

    const transaction = await screen.findByRole('region', { name: 'Transaction' })
    const labels = [...transaction.querySelectorAll('dt')].map((node) => node.textContent)
    expect(labels).toEqual(['Transaction id', 'Query name', 'Response code', 'Answer'])
    expect(transaction).toHaveTextContent('10.20.0.7')
    expect(transaction).toHaveTextContent('10.20.0.8')
  })

  it('shows what the description never claimed, under its own path', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))
    // Until the description arrives everything is undescribed, which is the honest thing to show.
    await screen.findByRole('region', { name: 'Transaction' })

    const extra = screen.getByRole('region', { name: 'Not described by the schema' })
    expect(extra).toHaveTextContent('dns.query.type')
    expect(extra).toHaveTextContent('dns.rcode.name')
    expect(extra).not.toHaveTextContent('dns.query.name')
  })

  it('still shows an older decoder’s values, as undescribed', async () => {
    renderView(session({ decoded: V1_DECODED }))

    const extra = await screen.findByRole('region', { name: 'Not described by the schema' })
    expect(extra).toHaveTextContent('dns.rcode')
    expect(extra).toHaveTextContent('example.org')
    await waitFor(() =>
      expect(screen.getByRole('region', { name: 'Transaction' })).toHaveTextContent(
        'Transaction id',
      ),
    )
  })

  it('says so when nothing was decoded', async () => {
    renderView(session())

    expect(await screen.findByText('Nothing was decoded')).toBeVisible()
  })

  it('states the detections, the carved files and the raw capture', () => {
    renderView(session())

    const facts = screen.getByRole('region', { name: 'What else was recorded' })
    expect(facts).toHaveTextContent('No rule fired')
    expect(facts).toHaveTextContent('No files were carved')
    expect(facts).toHaveTextContent('raw capture is still held')
  })

  it('says plainly when there is no such session', () => {
    renderView(NOT_FOUND)

    expect(screen.getByText('No such session')).toBeVisible()
    expect(screen.getByRole('button', { name: /back to results/i })).toBeVisible()
  })
})
