import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FlowTimeline } from './flow-timeline'

/** The real shape: bucket starts in epoch milliseconds, empty buckets left out. */
const SAMPLES = [
  {
    t: 1_761_531_489_000,
    bytes_up: 23_603_461,
    bytes_down: 11_782,
    packets_up: 16_860,
    packets_down: 9,
  },
  {
    t: 1_761_531_490_000,
    bytes_up: 26_211_386,
    bytes_down: 2_946,
    packets_up: 18_723,
    packets_down: 3,
  },
  // Two seconds of silence, then traffic again.
  { t: 1_761_531_493_000, bytes_up: 1_000, bytes_down: 500, packets_up: 4, packets_down: 2 },
]

function renderTimeline({
  samples = SAMPLES,
  bucketMs = 1_000,
  durationMs = 40_000,
  status = 200,
}: {
  samples?: unknown[]
  bucketMs?: number
  durationMs?: number
  status?: number
} = {}) {
  const asked: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input))
      if (status !== 200) return Response.json({ code: 'upstream' }, { status })
      return Response.json({ session_id: '7', bucket_ms: bucketMs, samples }, { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <FlowTimeline sessionId="7" durationMs={durationMs} />
    </QueryClientProvider>,
  )
  return asked
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FlowTimeline', () => {
  it('shows the traffic of the session in both directions', async () => {
    renderTimeline()

    const region = await screen.findByRole('region', { name: 'Traffic over time' })
    await waitFor(() => expect(region).toHaveTextContent(/up,/))
    expect(region).toHaveTextContent(/down, in buckets of 1 s/)
  })

  it('leaves the silence between two samples as a gap', async () => {
    renderTimeline()
    await screen.findByText(/in buckets of/)

    const offsets = [...document.querySelectorAll('[style*="left"]')].map(
      (node) => (node as HTMLElement).style.left,
    )
    // Three columns over a five-second span: at the start, one fifth in, and four fifths in.
    expect(offsets).toEqual(['0%', '20%', '80%'])
  })

  it('switches to packets without asking the server again', async () => {
    const asked = renderTimeline()
    await screen.findByText(/in buckets of/)
    expect(asked).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: 'packets' }))

    expect((await screen.findAllByText(/packets up/)).length).toBeGreaterThan(0)
    expect(asked).toHaveLength(1)
  })

  it('reads another width when one is chosen, and only then', async () => {
    const asked = renderTimeline()
    await screen.findByText(/in buckets of/)

    // The width it starts with suits this session; choosing a different one is what re-reads.
    await userEvent.click(screen.getByRole('button', { name: '5 s' }))

    await waitFor(() => expect(asked).toHaveLength(2))
    expect(asked[1]).toContain('bucket_ms=5000')
  })

  it('offers the numbers behind the picture, one focusable row per bucket', async () => {
    renderTimeline()
    await screen.findByText(/in buckets of/)

    // The header row is there for a screen reader only; the bucket rows are the focusable ones.
    const rows = screen.getAllByRole('row').filter((row) => row.hasAttribute('tabindex'))
    expect(rows).toHaveLength(SAMPLES.length)
    expect(rows[0]).toHaveAttribute('tabindex', '0')
    expect(rows[0]).toHaveTextContent(/up/)
    expect(rows[0]).toHaveTextContent(/down/)
  })

  it('says a session too short to plot is too short to plot', async () => {
    renderTimeline({
      samples: [
        {
          t: 1_761_562_864_000,
          bytes_up: 1_047,
          bytes_down: 5_902_936,
          packets_up: 3,
          packets_down: 4_219,
        },
      ],
      durationMs: 58,
      bucketMs: 100,
    })

    expect(await screen.findByText(/no shape to plot/)).toBeVisible()
  })

  it('says so when nothing was recorded over time', async () => {
    renderTimeline({ samples: [] })

    expect(await screen.findByText('No traffic was recorded over time')).toBeVisible()
  })

  it('keeps its failure to itself, with a retry', async () => {
    renderTimeline({ status: 503 })

    expect(await screen.findByRole('button', { name: /try again/i })).toBeVisible()
    // The heading and its controls are still there: the rest of the session is unaffected.
    expect(screen.getByRole('region', { name: 'Traffic over time' })).toBeVisible()
  })
})
