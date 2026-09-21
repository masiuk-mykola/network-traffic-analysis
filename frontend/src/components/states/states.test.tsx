import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HttpError } from '@api/http-error'

import { EmptyState, ErrorState, LoadingState } from './index'

async function httpError(body: Record<string, unknown>, init: ResponseInit): Promise<HttpError> {
  return HttpError.fromResponse(Response.json(body, init))
}

afterEach(() => {
  vi.useRealTimers()
})

describe('LoadingState', () => {
  it('announces that work is happening', () => {
    render(<LoadingState label="Loading sessions" />)

    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(status).toHaveTextContent('Loading sessions')
  })

  it('reads the same as a page and as a region', () => {
    const { rerender } = render(<LoadingState variant="region" />)
    expect(screen.getByRole('status')).toBeInTheDocument()

    rerender(<LoadingState variant="page" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})

describe('EmptyState', () => {
  it('is not an alert, so it cannot be mistaken for a failure', () => {
    render(<EmptyState title="No sessions match" description="Widen the time window." />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('No sessions match')).toBeInTheDocument()
  })

  it('offers the way back it was given', () => {
    render(
      <EmptyState title="Nothing here" action={<button type="button">Clear filters</button>} />,
    )

    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument()
  })
})

describe('ErrorState', () => {
  it('announces the failure', async () => {
    render(
      <ErrorState
        error={await httpError({ code: 'unavailable', detail: 'busy' }, { status: 503 })}
      />,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('retries when retrying can help', async () => {
    const onRetry = vi.fn()
    render(
      <ErrorState
        error={await httpError({ code: 'unavailable', detail: 'busy' }, { status: 503 })}
        onRetry={onRetry}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('offers no retry for a gone session, even when a handler is given', async () => {
    render(
      <ErrorState
        error={await httpError(
          { code: 'session_revoked', detail: 'sign in again' },
          { status: 401 },
        )}
        onRetry={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('offers no retry for a permission failure', async () => {
    render(
      <ErrorState
        error={await httpError({ code: 'forbidden', detail: 'observer' }, { status: 403 })}
        onRetry={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('waits out the delay the server asked for before enabling the retry', async () => {
    vi.useFakeTimers()
    const error = await httpError(
      { code: 'too_many_searches', detail: 'slow down' },
      { status: 429, headers: { 'retry-after': '3' } },
    )
    render(<ErrorState error={error} onRetry={vi.fn()} />)

    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Try again in 3 s')

    await vi.advanceTimersByTimeAsync(3000)

    expect(screen.getByRole('button')).toBeEnabled()
  })

  it('starts the countdown again when the next attempt is refused too', async () => {
    vi.useFakeTimers()
    const first = await httpError(
      { code: 'too_many_searches', detail: 'slow down' },
      { status: 429, headers: { 'retry-after': '3' } },
    )
    const { rerender } = render(<ErrorState error={first} onRetry={vi.fn()} />)

    await vi.advanceTimersByTimeAsync(3000)
    expect(screen.getByRole('button')).toBeEnabled()

    const second = await httpError(
      { code: 'too_many_searches', detail: 'slow down' },
      { status: 429, headers: { 'retry-after': '5' } },
    )
    rerender(<ErrorState error={second} onRetry={vi.fn()} />)

    expect(screen.getByRole('button')).toBeDisabled()
    expect(screen.getByRole('button')).toHaveTextContent('Try again in 5 s')
  })

  it('keeps our own contract failure generic and shows its code', async () => {
    render(
      <ErrorState
        error={await httpError(
          { code: 'upstream_contract', detail: 'unexpected response from the API' },
          { status: 502 },
        )}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('upstream_contract')
    expect(screen.getByRole('alert').textContent).not.toMatch(/schema|zod/i)
  })
})
