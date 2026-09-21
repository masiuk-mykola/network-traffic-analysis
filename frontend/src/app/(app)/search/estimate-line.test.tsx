import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EstimateLine } from './estimate-line'

const PARAMS = new URLSearchParams({ from: 'a', to: 'b', sensors: 'hq-core' })

function renderLine(respond: () => Promise<Response>, params: URLSearchParams | null = PARAMS) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      calls.push(String(input))
      return respond()
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <EstimateLine params={params} />
    </QueryClientProvider>,
  )
  return calls
}

const answer = (matches: number, scanned: number) => async () =>
  Response.json(
    { estimated_matches: matches, estimated_sessions_scanned: scanned, is_estimate: true },
    { status: 200 },
  )

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EstimateLine', () => {
  it('says roughly how many sessions match, and what answering would cost', async () => {
    renderLine(answer(12_431, 98_142))

    expect(await screen.findByText(/12,000 sessions match/)).toBeInTheDocument()
    expect(screen.getByText(/read about 98,142 sessions/)).toBeInTheDocument()
  })

  it('marks the number as approximate', async () => {
    renderLine(answer(12_431, 98_142))

    expect(await screen.findByText(/≈/)).toBeInTheDocument()
    expect(screen.getByText(/estimated from a sample/i)).toBeInTheDocument()
  })

  it('says plainly when nothing matches', async () => {
    renderLine(answer(0, 98_142))

    expect(await screen.findByText('No sessions match this query')).toBeInTheDocument()
  })

  it('asks for nothing while the query cannot be run', () => {
    const calls = renderLine(answer(1, 1), null)

    expect(calls).toHaveLength(0)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows no number at all while it is fetching', () => {
    renderLine(() => new Promise<Response>(() => {}))

    expect(screen.getByRole('status')).toHaveTextContent('Estimating')
    expect(screen.queryByText(/sessions match/)).not.toBeInTheDocument()
  })

  it('reports a failure without taking over the form', async () => {
    renderLine(async () => Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('does not invite another attempt while the server is refusing them', async () => {
    renderLine(async () =>
      Response.json(
        { code: 'estimate_rate_limited', detail: 'slow down' },
        { status: 429, headers: { 'retry-after': '2' } },
      ),
    )

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many requests')
    expect(alert.querySelector('button')).toBeNull()
  })
})
