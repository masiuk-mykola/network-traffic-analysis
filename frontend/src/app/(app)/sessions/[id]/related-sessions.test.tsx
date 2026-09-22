import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RelatedSessions } from './related-sessions'

vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

/** The real shape of a related row, as the server sends it. */
const row = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  sensor_id: 'hq-core',
  start: '2025-10-27T11:25:24.401Z',
  end: '2025-10-27T11:25:24.407Z',
  duration_ms: 6,
  protocol: 'tcp',
  transport: 'tcp',
  src: { ip: '10.20.9.250', port: 55425, host: 'scan-it-01.quillmere.example' },
  dst: { ip: '10.20.4.41', port: 139 },
  bytes: { up: 74, down: 54 },
  packets: { up: 1, down: 1 },
  risk: { score: 12, band: 'low', reasons: [] },
  summary: 'TCP',
  decoder: 'tcp/2',
  files_count: 0,
  pcap_available: true,
  ...over,
})

function renderList(pages: Array<Record<string, unknown>> | { status: number }) {
  const asked: string[] = []
  let index = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input))
      if (!Array.isArray(pages))
        return Response.json({ code: 'upstream' }, { status: pages.status })
      const page = pages[Math.min(index, pages.length - 1)]
      index += 1
      return Response.json(page, { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RelatedSessions sessionId="72057639299711028" />
    </QueryClientProvider>,
  )
  return asked
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RelatedSessions', () => {
  it('lists what the server relates to this session, as links to those sessions', async () => {
    renderList([
      { items: [row('72057639299711033'), row('216172827537047572')], next_cursor: null },
    ])

    const list = await screen.findByRole('table', { name: 'Related sessions' })
    const links = screen.getAllByRole('link')
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/sessions/72057639299711033',
      '/sessions/216172827537047572',
    ])
    expect(list).toHaveTextContent('scan-it-01.quillmere.example:55425')
    expect(list).toHaveTextContent('10.20.4.41:139')
    expect(list).toHaveTextContent('128 B')
    expect(list).toHaveTextContent('risk 12 (low)')
  })

  it('starts within an hour and re-reads when another window is chosen', async () => {
    const asked = renderList([{ items: [row('7')], next_cursor: null }])
    await screen.findByRole('table', { name: 'Related sessions' })
    expect(asked[0]).toContain('window=1h')

    await userEvent.click(screen.getByRole('button', { name: '6 hours' }))

    await waitFor(() => expect(asked).toHaveLength(2))
    expect(asked[1]).toContain('window=6h')
  })

  it('reads on when the server says there is more, and appends what comes back', async () => {
    const asked = renderList([
      { items: [row('7')], next_cursor: 'more' },
      { items: [row('8')], next_cursor: null },
    ])
    await screen.findByRole('table', { name: 'Related sessions' })

    await userEvent.click(screen.getByRole('button', { name: 'Read on' }))

    await waitFor(() => expect(screen.getAllByRole('link')).toHaveLength(2))
    expect(asked[1]).toContain('cursor=more')
  })

  it('says when there is nothing around this session', async () => {
    renderList([{ items: [], next_cursor: null }])

    expect(await screen.findByText('Nothing else in this window')).toBeVisible()
  })

  it('keeps a failure to itself, with a retry', async () => {
    renderList({ status: 503 })

    expect(await screen.findByRole('button', { name: /try again/i })).toBeVisible()
    expect(screen.getByRole('region', { name: 'Related sessions' })).toBeVisible()
  })

  it('states a session the server does not have, without offering a retry', async () => {
    renderList({ status: 404 })

    expect(await screen.findByText(/nothing around this session/i)).toBeVisible()
    expect(screen.queryByRole('button', { name: /try again/i })).toBeNull()
  })

  it('claims no reason for the relationship', async () => {
    renderList([{ items: [row('7')], next_cursor: null }])
    const list = await screen.findByRole('table', { name: 'Related sessions' })

    expect(list.textContent).not.toMatch(/because|related by|same |reason/i)
  })
})
