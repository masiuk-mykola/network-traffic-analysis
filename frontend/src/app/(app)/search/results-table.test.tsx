import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MISSING, type SearchStatus } from '@lib/search/search-state'
import type { SortKey } from '@lib/search/sort'

import { ResultsTable } from './results-table'

vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

const COLUMNS = {
  items: [
    {
      key: 'start',
      label: 'Start',
      type: 'ts',
      default_visible: true,
      sortable: true,
      width_hint: 190,
    },
    {
      key: 'src',
      label: 'Source',
      type: 'ip_port',
      default_visible: true,
      sortable: false,
      width_hint: 190,
    },
    {
      key: 'summary',
      label: 'Summary',
      type: 'text',
      default_visible: true,
      sortable: false,
      width_hint: 360,
    },
    {
      key: 'bytes',
      label: 'Bytes',
      type: 'bytes',
      default_visible: true,
      sortable: true,
      width_hint: 120,
    },
    {
      key: 'dst_country',
      label: 'Destination country',
      type: 'geo_hint',
      default_visible: true,
      sortable: false,
      width_hint: 140,
    },
    {
      key: 'id',
      label: 'Session id',
      type: 'id',
      default_visible: false,
      sortable: false,
      width_hint: 190,
    },
  ],
}

const row = (id: string) => ({
  id,
  sensor_id: 'hq-core',
  start: '2025-10-27T11:59:54.117Z',
  end: '2025-10-27T11:59:55.193Z',
  duration_ms: 1076,
  protocol: 'tls',
  transport: 'tcp',
  src: { ip: '10.20.2.25', port: 37065 },
  dst: { ip: '192.0.2.104', port: 443, country: 'AT' },
  bytes: { up: 1, down: 2 },
  packets: { up: 1, down: 1 },
  risk: { score: 10, band: 'low', reasons: [] },
  summary: `session ${id}`,
  decoder: 'tls/2',
  files_count: 0,
  pcap_available: true,
})

const running = { state: 'running' } as unknown as SearchStatus
const finished = { state: 'done' } as unknown as SearchStatus

function renderTable(
  results: Record<string, unknown> | (() => Promise<Response>),
  status: SearchStatus = finished,
  { sort = '-ts', onSortChange }: { sort?: SortKey; onSortChange?: (sort: SortKey) => void } = {},
) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      if (url.includes('meta/columns')) return Response.json(COLUMNS, { status: 200 })
      return typeof results === 'function' ? results() : Response.json(results, { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ResultsTable
        searchId="srch-1"
        status={status}
        sort={sort}
        onSortChange={onSortChange ?? (() => {})}
      />
    </QueryClientProvider>,
  )
  return calls
}

const page = (items: unknown[], over: Record<string, unknown> = {}) => ({
  items,
  next_cursor: null,
  complete: true,
  matched_so_far: items.length,
  ...over,
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ResultsTable', () => {
  it('asks for nothing without a search', () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        calls.push(String(input))
        return Response.json(COLUMNS, { status: 200 })
      }),
    )
    const client = new QueryClient()
    render(
      <QueryClientProvider client={client}>
        <ResultsTable searchId={null} status={undefined} sort="-ts" onSortChange={() => {}} />
      </QueryClientProvider>,
    )

    expect(calls.filter((url) => url.includes('/results'))).toEqual([])
  })

  it('builds its header from the columns the server publishes', async () => {
    renderTable(page([row('1')]))

    expect(await screen.findByRole('columnheader', { name: 'Start' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Destination country' })).toBeInTheDocument()
    // Published but hidden by default.
    expect(screen.queryByRole('columnheader', { name: 'Session id' })).not.toBeInTheDocument()
  })

  it('renders a column whose type this server never documented', async () => {
    renderTable(page([row('1')]))

    expect(await screen.findByText('AT')).toBeInTheDocument()
  })

  it('keeps only a window of rows in the document', async () => {
    const many = Array.from({ length: 5000 }, (_, index) => row(String(index + 1)))
    renderTable(page(many))

    await screen.findByRole('table')
    await waitFor(() => expect(screen.getAllByRole('row').length).toBeGreaterThan(1))
    // The header plus a window, nowhere near five thousand.
    expect(screen.getAllByRole('row').length).toBeLessThan(100)
  })

  it('says it is still looking while the job runs with nothing yet', async () => {
    renderTable(page([], { complete: false }), running)

    expect(await screen.findByText(/still looking/i)).toBeInTheDocument()
  })

  it('says plainly when a finished search matched nothing', async () => {
    renderTable(page([]))

    expect(await screen.findByText('No sessions matched')).toBeInTheDocument()
  })

  it('says when that was everything', async () => {
    renderTable(page([row('1')]))

    expect(await screen.findByText(/that is every session/i)).toBeInTheDocument()
  })

  it('keeps the rows it has when a later page fails', async () => {
    let asked = 0
    renderTable(async () => {
      asked += 1
      return asked === 1
        ? Response.json(page([row('1')], { next_cursor: 'c1', complete: false }), { status: 200 })
        : Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 })
    })

    await screen.findByText('session 1')

    // Reaching the end of what is loaded asks for the next page on its own; that one fails.
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('session 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('leads each row to its session', async () => {
    renderTable(page([row('72057639335362590')]))

    const link = await screen.findByRole('row', { name: /session 72057639335362590/ })
    expect(link).toHaveAttribute('href', '/sessions/72057639335362590')
  })

  it('offers sorting only once the search has finished', async () => {
    renderTable(page([row('1')], { complete: false }), running)

    expect(await screen.findByRole('button', { name: 'Start' })).toBeDisabled()
  })

  it('sorts on a column the server publishes as sortable', async () => {
    const changes: SortKey[] = []
    renderTable(page([row('1')]), finished, { onSortChange: (sort) => changes.push(sort) })
    await screen.findByRole('table')

    await userEvent.click(screen.getByRole('button', { name: /bytes/i }))

    expect(changes).toEqual(['-bytes'])
  })

  it('marks the order in force and offers no control on the other columns', async () => {
    renderTable(page([row('1')]), finished, { sort: '-bytes' })
    await screen.findByRole('table')

    expect(screen.getByRole('columnheader', { name: /bytes/i })).toHaveAttribute(
      'aria-sort',
      'descending',
    )
    expect(screen.queryByRole('button', { name: 'Summary' })).toBeNull()
  })

  it('refuses a different order while the job is still running, and says why', async () => {
    renderTable(page([row('1')], { complete: false }), running)
    await screen.findByRole('table')

    const control = screen.getByRole('button', { name: /bytes/i })
    expect(control).toBeDisabled()
    expect(control).toHaveAttribute('title', 'A different order needs a finished search')
  })

  it('asks for no rows at all when the server no longer has the job', async () => {
    const calls = renderTable(page([row('1')]), MISSING)

    await waitFor(() => expect(calls.length).toBeGreaterThan(0))
    expect(calls.filter((url) => url.includes('/results'))).toEqual([])
  })
})
