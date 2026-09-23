import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EMPTY_QUERY, parseQuery } from '@lib/search/query-params'

import { QueryForm } from './query-form'

const replace = vi.fn()
const push = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push, refresh: vi.fn() }),
}))

const SENSORS = {
  items: [
    {
      id: 'hq-core',
      name: 'HQ Core',
      site: 'Lisbon HQ',
      kind: 'tap',
      status: 'online',
      decoder_version: 'v2',
      tz: 'Europe/Lisbon',
      retention: { metadata_days: 30, pcap_hours: 48, files_days: 7 },
      last_packet_at: '2025-10-27T12:00:00.000Z',
      lag_seconds: 2,
    },
    {
      id: 'harbor-branch',
      name: 'Harbor Branch',
      site: 'Porto',
      kind: 'span',
      status: 'lagging',
      decoder_version: 'v1',
      tz: 'Europe/Berlin',
      retention: { metadata_days: 30, pcap_hours: 48, files_days: 7 },
      last_packet_at: '2025-10-27T11:55:00.000Z',
      lag_seconds: 300,
    },
  ],
}

/** Both points, unless a test says this account may read fewer. */
const READABLE = ['hq-core', 'harbor-branch']

function renderForm(
  response: () => Promise<Response>,
  { readable = READABLE, initial = EMPTY_QUERY } = {},
) {
  vi.stubGlobal('fetch', vi.fn(response))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <QueryForm initial={initial} readable={readable} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  replace.mockClear()
  push.mockClear()
  // The form only writes to the address while it is the screen the address names.
  window.history.replaceState(null, '', '/search')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('QueryForm', () => {
  it('cannot be submitted while the points are loading, and says where the wait is', async () => {
    renderForm(() => new Promise<Response>(() => {}))

    expect(await screen.findByText('Loading capture points')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run search' })).toBeDisabled()
  })

  it('keeps the rest of the form when the points cannot be fetched', async () => {
    renderForm(async () => Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    // The control is there whether it is offering a retry or in the middle of one.
    expect(
      (await screen.findAllByRole('button', { name: /try(ing)? again/i })).length,
    ).toBeGreaterThan(0)
    // The failure belongs to the capture points; the rest of the screen is still worth having.
    expect(screen.getByLabelText('From (UTC)')).toBeInTheDocument()
    expect(screen.getByLabelText('To (UTC)')).toBeInTheDocument()
    // And nothing can be started from a list that never arrived.
    expect(screen.getByRole('button', { name: 'Run search' })).toBeDisabled()
  })

  it('says so when the account may read none', async () => {
    renderForm(async () => Response.json({ items: [] }, { status: 200 }))

    expect(await screen.findByText('No capture points to search')).toBeInTheDocument()
  })

  it('refuses to search nowhere', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Choose at least one capture point.')
    expect(screen.getByRole('button', { name: 'Run search' })).toBeDisabled()
  })

  it('marks the point that is behind', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))

    const row = (await screen.findByText('Harbor Branch')).closest('li')
    expect(row).toHaveTextContent('behind 5 m 00 s')
  })

  it('suggests a window that ends at the last traffic, not today', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))

    const to = await screen.findByLabelText('To (UTC)')
    // The window is derived from the points, so it fills in once they arrive.
    await waitFor(() => expect(to).toHaveValue('2025-10-27T12:00'))
  })

  it('offers spans that end at the last traffic, and marks the one in use', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))

    const lastDay = await screen.findByRole('button', { name: 'Last 24 h' })
    await waitFor(() => expect(lastDay).toBeEnabled())
    expect(screen.getByRole('button', { name: 'Last 6 h' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(lastDay)

    expect(screen.getByLabelText('From (UTC)')).toHaveValue('2025-10-26T12:00')
    expect(screen.getByLabelText('To (UTC)')).toHaveValue('2025-10-27T12:00')
    expect(lastDay).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(window.location.search).toContain('from=2025-10-26T12'))
  })

  it('mirrors the choices into the address bar without a round trip', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))
    await screen.findByText('HQ Core')

    await userEvent.click(screen.getAllByRole('checkbox')[0]!)

    await waitFor(() => expect(window.location.search).toContain('sensor=hq-core'))
    // Going through the router would re-render the page on the server for every change.
    expect(replace).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('refuses a window that ends before it starts', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))
    await screen.findByText('HQ Core')
    await userEvent.click(screen.getAllByRole('checkbox')[0]!)

    const from = screen.getByLabelText('From (UTC)')
    fireEvent.change(from, { target: { value: '2025-10-27T23:00' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('The window ends before it starts.')
  })
  it('lets a point this account may read be chosen', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }))
    await screen.findByText('HQ Core')

    const box = within(rowFor('HQ Core')).getByRole('checkbox')
    expect(box).toBeEnabled()
    await userEvent.click(box)

    expect(box).toBeChecked()
    await waitFor(() => expect(window.location.search).toContain('sensor=hq-core'))
  })

  it('shows a point this account cannot read, shut, and says why', async () => {
    // The server publishes every point there is; only the profile says which are ours to read.
    renderForm(async () => Response.json(SENSORS, { status: 200 }), { readable: ['hq-core'] })
    await screen.findByText('Harbor Branch')

    const row = rowFor('Harbor Branch')
    expect(row).toHaveTextContent('No access')
    const box = within(row).getByRole('checkbox')
    expect(box).toBeDisabled()
    // The reason is read out with the box rather than left to the eye alone.
    expect(box).toHaveAccessibleDescription('No access')
  })

  it('does not let a point this account cannot read be chosen', async () => {
    renderForm(async () => Response.json(SENSORS, { status: 200 }), { readable: ['hq-core'] })
    await screen.findByText('Harbor Branch')

    const box = within(rowFor('Harbor Branch')).getByRole('checkbox')
    await userEvent.click(box)

    expect(box).not.toBeChecked()
    expect(window.location.search).not.toContain('harbor-branch')
  })

  it('does not take a point from the address that this account cannot read', async () => {
    // What the address named is filtered before it ever reaches the form, so it arrives as what it
    // is — not a choice — and nothing here turns it back into one.
    const fromLink = parseQuery(new URLSearchParams('sensor=harbor-branch'), ['hq-core'])
    expect(fromLink.sensorIds).toEqual([])

    renderForm(async () => Response.json(SENSORS, { status: 200 }), {
      readable: ['hq-core'],
      initial: fromLink,
    })
    await screen.findByText('Harbor Branch')

    expect(within(rowFor('Harbor Branch')).getByRole('checkbox')).not.toBeChecked()
    expect(window.location.search).not.toContain('harbor-branch')
  })
})

function rowFor(name: string): HTMLElement {
  const row = screen.getByText(name).closest('li')
  if (!row) throw new Error(`no row for ${name}`)
  return row
}
