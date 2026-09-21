import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { components } from '@api/schema'
import type { FieldCatalogue } from '@lib/search/condition'
import { EMPTY_QUERY, type QueryState } from '@lib/search/query-params'

import { RunControl } from './run-control'

type Search = components['schemas']['Search']

const FIELDS: FieldCatalogue = {}

const READY: QueryState = {
  ...EMPTY_QUERY,
  sensorIds: ['hq-core'],
  from: '2025-10-27T06:00:00.000Z',
  to: '2025-10-27T12:00:00.000Z',
}

const JOB = {
  id: 'srch-1',
  state: 'running',
  sensor_ids: ['hq-core'],
  from: READY.from,
  to: READY.to,
  filter: { all: [] },
  sort: '-ts',
  created_at: '2025-10-27T12:00:00.000Z',
  progress: { matched: 12, percent: 20 },
  stats: { matched_bytes_up: 0, matched_bytes_down: 0 },
  warnings: [],
} as unknown as Search

type Call = { url: string; method: string; label: string | null }

function renderControl(
  respond: (call: Call) => Promise<Response>,
  props: Partial<Parameters<typeof RunControl>[0]> = {},
) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers)
      const call = {
        url: String(input),
        method: init?.method ?? 'GET',
        label: headers.get('idempotency-key'),
      }
      calls.push(call)
      return respond(call)
    }),
  )
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const onStarted = vi.fn()
  const view = (query: QueryState) => (
    <QueryClientProvider client={client}>
      <RunControl
        query={query}
        fields={FIELDS}
        problem={null}
        running={undefined}
        onStarted={onStarted}
        {...props}
      />
    </QueryClientProvider>
  )
  const { rerender } = render(view(READY))

  return { calls, onStarted, useQuery: (query: QueryState) => rerender(view(query)) }
}

const started = async () => Response.json(JOB, { status: 202 })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RunControl', () => {
  it('starts a search and reports the job', async () => {
    const { calls, onStarted } = renderControl(started)

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(JOB))
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
    expect(calls[0]?.label).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
  })

  it('cannot be pressed into two jobs', async () => {
    let release: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const { calls } = renderControl(() => pending)

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))
    const button = await screen.findByRole('button', { name: /starting/i })
    expect(button).toBeDisabled()
    await userEvent.click(button)

    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
    release(await started())
  })

  it('labels a retry the same way, so the server replays instead of duplicating', async () => {
    const { calls } = renderControl(async (call) =>
      calls.filter((c) => c.method === 'POST').length === 1
        ? Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 })
        : started(),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))

    await waitFor(() => {
      const posts = calls.filter((call) => call.method === 'POST')
      expect(posts).toHaveLength(2)
      expect(posts[0]?.label).toBe(posts[1]?.label)
    })
  })

  it('does not start the same search twice', async () => {
    const { calls } = renderControl(started)

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    await userEvent.click(await screen.findByRole('button', { name: 'Run search' }))

    // An identical body seconds apart is a duplicate job to the API, and cancelling the first to
    // re-create it is worse: a cancelled label is not replayed, so that really would be two jobs.
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(1)
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false)
  })

  it('frees the previous slot once the query has changed', async () => {
    const { calls, useQuery } = renderControl(started)

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))

    // A different query hashes to a different label, so this really is another search.
    useQuery({ ...READY, sensorIds: ['hq-core', 'dc-east'] })
    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))

    await waitFor(() =>
      expect(calls.map((call) => call.method)).toEqual(['POST', 'DELETE', 'POST']),
    )
  })

  it('explains a refusal for want of a slot and waits out the stated delay', async () => {
    renderControl(async () =>
      Response.json(
        { code: 'too_many_searches', detail: 'three already running' },
        { status: 429, headers: { 'retry-after': '5' } },
      ),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Run search' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests')
    expect(await screen.findByRole('button', { name: /try again in \d+ s/i })).toBeDisabled()
  })

  it('shows what the job warns about', () => {
    renderControl(started, {
      running: {
        ...JOB,
        warnings: [
          { code: 'sensor_unreadable', sensor_id: 'harbor-branch', detail: 'Point unreadable' },
        ],
      } as unknown as Search,
    })

    expect(screen.getByText(/point unreadable/i)).toBeInTheDocument()
  })

  it('stays disabled while the query is not runnable', () => {
    renderControl(started, { problem: 'Choose at least one capture point.' })

    expect(screen.getByRole('button', { name: 'Run search' })).toBeDisabled()
  })
})
