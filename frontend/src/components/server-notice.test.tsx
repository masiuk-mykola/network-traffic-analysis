import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ServerNotice } from './server-notice'

const health = (components: Record<string, unknown>) => ({
  status: 'degraded',
  components,
  server_time: '2025-10-27T12:00:00.000Z',
  version: '1.0.0',
})

const WELL = { ...health({ index: { status: 'ok' } }), status: 'ok' }
const REBUILDING = health({
  index: { status: 'degraded', detail: 'The session index is rebuilding; searches may be slow.' },
})

function renderNotice(reply: () => Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => reply()),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ServerNotice />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ServerNotice', () => {
  it('quotes the server while a part of it is unwell', async () => {
    renderNotice(async () => Response.json(REBUILDING))

    const notice = await screen.findByRole('status', { name: 'Server condition' })
    expect(notice).toHaveTextContent('The session index is rebuilding; searches may be slow.')
    expect(notice).toHaveTextContent('index')
  })

  it('says nothing at all while the server is well', async () => {
    renderNotice(async () => Response.json(WELL))

    // Give the read time to land before concluding there is nothing to show.
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole('status', { name: 'Server condition' })).toBeNull()
  })

  it('says nothing when the server cannot be asked', async () => {
    renderNotice(async () => Response.json({ code: 'unavailable' }, { status: 503 }))

    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
  })

  it('can be dismissed, and stays dismissed for that condition', async () => {
    renderNotice(async () => Response.json(REBUILDING))
    await screen.findByRole('status', { name: 'Server condition' })

    await userEvent.click(screen.getByRole('button', { name: /dismiss/i }))

    expect(screen.queryByRole('status', { name: 'Server condition' })).toBeNull()
  })

  it('names a part the server gave no sentence for', async () => {
    renderNotice(async () => Response.json(health({ pcap_store: { status: 'degraded' } })))

    expect(await screen.findByRole('status', { name: 'Server condition' })).toHaveTextContent(
      'pcap_store',
    )
  })
})
