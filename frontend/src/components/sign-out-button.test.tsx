import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SignOutButton } from './sign-out-button'

const replace = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
}))

let client: QueryClient

function renderButton() {
  client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <SignOutButton />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  replace.mockClear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(null, { status: 204 })),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SignOutButton', () => {
  it('asks before ending the session', async () => {
    renderButton()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByRole('dialog')).toHaveTextContent('Sign out?')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('does nothing when the person stays', async () => {
    renderButton()

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Stay signed in' }))

    expect(fetch).not.toHaveBeenCalled()
    expect(replace).not.toHaveBeenCalled()
  })

  it('ends the session, drops what was cached, and leaves', async () => {
    renderButton()
    client.setQueryData(['sensors'], { items: [] })

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', { method: 'POST' })
    expect(client.getQueryData(['sensors'])).toBeUndefined()
  })
})
