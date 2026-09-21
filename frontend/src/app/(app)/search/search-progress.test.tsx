import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { EXPIRED, type Search, type SearchStatus } from '@lib/search/search-state'

import { SearchProgress } from './search-progress'

const JOB = {
  id: 'srch-1',
  state: 'running',
  sensor_ids: ['hq-core'],
  from: '2025-10-27T06:00:00.000Z',
  to: '2025-10-27T12:00:00.000Z',
  filter: { all: [] },
  sort: '-ts',
  created_at: '2025-10-27T12:00:00.000Z',
  progress: { percent: 40, scanned_sessions: 4000, total_sessions_estimate: 10_000, matched: 12 },
  stats: { matched_bytes_up: 0, matched_bytes_down: 0 },
  warnings: [],
} as unknown as Search

const job = (over: Record<string, unknown>): Search => ({ ...JOB, ...over }) as unknown as Search

function renderProgress(
  props: Partial<Parameters<typeof SearchProgress>[0]> = {},
  respond: () => Promise<Response> = async () => new Response(null, { status: 204 }),
) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
      return respond()
    }),
  )
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SearchProgress
        searchId="srch-1"
        status={JOB as SearchStatus}
        error={null}
        isPending={false}
        {...props}
      />
    </QueryClientProvider>,
  )
  return calls
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SearchProgress', () => {
  it('asks nothing and shows nothing without a job', () => {
    const calls = renderProgress({ searchId: null, status: undefined })

    expect(calls).toEqual([])
    expect(screen.queryByRole('region', { name: 'Search progress' })).not.toBeInTheDocument()
  })

  it('says the search is starting before the first report arrives', () => {
    renderProgress({ status: undefined, isPending: true })

    expect(screen.getByRole('status')).toHaveTextContent('Starting the search')
  })

  it('shows how far a running job has got', () => {
    renderProgress()

    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
    expect(screen.getByText(/scanned 4,000 of about 10,000/i)).toBeInTheDocument()
    expect(screen.getByText('12 matched')).toBeInTheDocument()
  })

  it('marks a match count the server called an estimate', () => {
    renderProgress({
      status: job({ progress: { ...JOB.progress, matched: 900, matched_is_estimate: true } }),
    })

    expect(screen.getByText(/900 matched so far/)).toBeInTheDocument()
    expect(screen.getByText('(estimated)')).toBeInTheDocument()
  })

  it('reports a finished job and stops offering to stop it', () => {
    renderProgress({ status: job({ state: 'done' }) })

    expect(screen.getByText('Search finished')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
  })

  it('says why a job failed when the server said', () => {
    renderProgress({ status: job({ state: 'failed', error: { detail: 'decoder exploded' } }) })

    expect(screen.getByText('Search failed')).toBeInTheDocument()
    expect(screen.getByText('decoder exploded')).toBeInTheDocument()
  })

  it('treats a discarded job as its own thing, not a failure', () => {
    renderProgress({ status: EXPIRED })

    expect(screen.getByText('Search discarded')).toBeInTheDocument()
    expect(screen.getByText(/run it again/i)).toBeInTheDocument()
    expect(screen.queryByText('Search failed')).not.toBeInTheDocument()
  })

  it('stops a running search when asked', async () => {
    const calls = renderProgress()

    await userEvent.click(screen.getByRole('button', { name: 'Stop' }))

    await waitFor(() => expect(calls).toContain('DELETE /api/searches/srch-1'))
  })

  it('reports a failed reading without pretending the search stopped', () => {
    renderProgress({ error: new Error('network') })

    expect(screen.getByRole('alert')).toHaveTextContent('Still watching')
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })
})
