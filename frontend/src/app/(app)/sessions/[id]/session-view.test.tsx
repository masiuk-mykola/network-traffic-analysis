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
    flags: { qr: true, aa: true, tc: false, rd: true, ra: true },
    answers: [
      { name: 'prn-16.quillmere.example', type: 'A', ttl: 3600, data: '10.20.0.7' },
      { name: 'prn-16.quillmere.example', type: 'A', ttl: 60, data: '10.20.0.8' },
    ],
  },
}

// The older decoder: a scalar where the description expects an object, an object where it expects
// a list.
const V1_DECODED = {
  dns: {
    transaction_id: '6001',
    query: { name: 'c81e40ba.packages.example.net', type: 'A', class: 'IN' },
    rcode: '3',
    flags: { qr: true, rd: true, ra: true },
    authority: { name: 'example.org', type: 'SOA', ttl: '3600' },
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

const NXDOMAIN_RISK = {
  score: 36,
  band: 'low',
  reasons: [{ code: 'nxdomain_burst', label: 'Burst of NXDOMAIN answers', mitre: 'T1568.002' }],
}

describe('SessionView, for a DNS session', () => {
  it('reads as an exchange: the question, the response, and the records', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))

    const exchange = await screen.findByRole('region', { name: 'DNS exchange' })
    expect(exchange).toHaveTextContent('prn-16.quillmere.example')
    expect(exchange).toHaveTextContent('NOERROR')
    expect(exchange).toHaveTextContent('Answers')
    expect(exchange).toHaveTextContent('10.20.0.7')
  })

  it('names a response code the older decoder gave as a bare number', async () => {
    renderView(session({ decoded: V1_DECODED }))

    expect(await screen.findByRole('region', { name: 'DNS exchange' })).toHaveTextContent(
      'NXDOMAIN',
    )
  })

  it('shows the single authority record the older decoder carries', async () => {
    renderView(session({ decoded: V1_DECODED }))

    const exchange = await screen.findByRole('region', { name: 'DNS exchange' })
    expect(exchange).toHaveTextContent('Authority')
    expect(exchange).toHaveTextContent('example.org')
  })

  it('states the flags that are set, in words', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))

    expect(await screen.findByRole('region', { name: 'DNS exchange' })).toHaveTextContent(
      'response, authoritative, recursion desired, recursion available',
    )
  })

  it('carries the server’s reason for the risk next to the transaction', async () => {
    renderView(session({ decoded: V1_DECODED, risk: NXDOMAIN_RISK }))

    const flagged = await screen.findByRole('list', { name: 'What the server flagged' })
    expect(flagged).toHaveTextContent('Burst of NXDOMAIN answers')
    expect(flagged).toHaveTextContent('T1568.002')
  })

  it('offers to copy the name that was asked for', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))

    await screen.findByRole('region', { name: 'DNS exchange' })
    expect(screen.getByRole('button', { name: 'Copy name' })).toBeVisible()
  })

  it('still shows everything decoded, including what the layout does not place', async () => {
    renderView(session({ decoded: V2_DECODED, decoder: 'dns/2' }))

    await screen.findByRole('region', { name: 'DNS exchange' })
    expect(await screen.findByRole('region', { name: 'Transaction' })).toHaveTextContent(
      'Transaction id',
    )
    expect(screen.getByRole('region', { name: 'Not described by the schema' })).toHaveTextContent(
      'dns.query.type',
    )
  })
})

describe('SessionView, read by an observer', () => {
  it('says a withheld value is withheld, and shows nothing of it', async () => {
    renderView(
      session({
        protocol: 'http',
        decoder: 'http/2',
        // What the server actually sends an observer in place of a sensitive header.
        decoded: {
          http: {
            method: 'GET',
            request_headers: [
              { name: 'Host', value: 'prn-03' },
              { name: 'Cookie', value: { redacted: true } },
            ],
          },
        },
      }),
    )

    const extra = await screen.findByRole('region', { name: 'Not described by the schema' })
    expect(extra).toHaveTextContent('Withheld for your role')
    expect(extra).not.toHaveTextContent('redacted')
    // The reader still learns which field it was.
    expect(extra).toHaveTextContent('http.request_headers[1].value')
  })
})

describe('SessionView, for any other protocol', () => {
  it('has no exchange, and the generic view as before', async () => {
    renderView(
      session({
        protocol: 'tls',
        decoder: 'tls/2',
        decoded: { tls: { sni: 'ads.example.net', version: 'TLS1.2' } },
      }),
    )

    await screen.findByRole('region', { name: 'Not described by the schema' })
    expect(screen.queryByRole('region', { name: 'DNS exchange' })).toBeNull()
    expect(screen.getByRole('region', { name: 'Not described by the schema' })).toHaveTextContent(
      'ads.example.net',
    )
  })
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

  it('loses the session but not the screen when the read fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 })),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SessionView sessionId="72057639299711028" />
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    // The way back is the one thing that must never be lost to a failed read.
    expect(screen.getByRole('button', { name: /back to results/i })).toBeVisible()
    expect(await screen.findByRole('button', { name: /try(ing)? again/i })).toBeInTheDocument()
  })

  it('says plainly when there is no such session', () => {
    renderView(NOT_FOUND)

    expect(screen.getByText('No such session')).toBeVisible()
    expect(screen.getByRole('button', { name: /back to results/i })).toBeVisible()
  })
})
