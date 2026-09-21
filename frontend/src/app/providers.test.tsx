import { useQuery } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HttpError } from '@api/http-error'

import { Providers } from './providers'

const replace = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
}))

async function failWith(body: Record<string, unknown>, status: number): Promise<never> {
  throw await HttpError.fromResponse(Response.json(body, { status }))
}

function Screen({ queryFn }: { queryFn: () => Promise<never> }) {
  const first = useQuery({ queryKey: ['a'], queryFn, retry: false })
  const second = useQuery({ queryKey: ['b'], queryFn, retry: false })
  return <p>{`${first.status} ${second.status}`}</p>
}

beforeEach(() => {
  replace.mockClear()
  window.history.pushState({}, '', '/search')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the reaction to a dead session', () => {
  it('leaves for sign in, remembering where it happened', async () => {
    window.history.pushState({}, '', '/sessions/72075232438042624')

    render(
      <Providers>
        <Screen queryFn={() => failWith({ code: 'session_revoked', detail: 'gone' }, 401)} />
      </Providers>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalled())
    expect(replace).toHaveBeenCalledWith('/login?next=%2Fsessions%2F72075232438042624')
  })

  it('reacts once even when two queries fail together', async () => {
    render(
      <Providers>
        <Screen queryFn={() => failWith({ code: 'session_revoked', detail: 'gone' }, 401)} />
      </Providers>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalled())
    expect(replace).toHaveBeenCalledOnce()
  })

  it('explains itself', async () => {
    render(
      <Providers>
        <Screen queryFn={() => failWith({ code: 'session_revoked', detail: 'gone' }, 401)} />
      </Providers>,
    )

    expect(await screen.findByText('Your session ended')).toBeInTheDocument()
  })

  it('leaves a struggling server alone', async () => {
    render(
      <Providers>
        <Screen queryFn={() => failWith({ code: 'unavailable', detail: 'busy' }, 503)} />
      </Providers>,
    )

    await waitFor(() => expect(screen.getByText(/error/)).toBeInTheDocument())
    expect(replace).not.toHaveBeenCalled()
  })

  it('stays put when the app is already at sign in', async () => {
    window.history.pushState({}, '', '/login')

    render(
      <Providers>
        <Screen queryFn={() => failWith({ code: 'session_revoked', detail: 'gone' }, 401)} />
      </Providers>,
    )

    await waitFor(() => expect(screen.getByText(/error/)).toBeInTheDocument())
    expect(replace).not.toHaveBeenCalled()
  })
})
