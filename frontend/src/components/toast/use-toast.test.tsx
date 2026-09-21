import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { HttpError } from '@api/http-error'

import { ToastProvider } from './toast-provider'
import { useToast } from './use-toast'

function Probe({ onFailure }: { onFailure?: unknown }) {
  const { notify, notifyFailure } = useToast()
  return (
    <>
      <button type="button" onClick={() => notify({ title: 'Search cancelled' })}>
        info
      </button>
      <button type="button" onClick={() => notifyFailure(onFailure)}>
        failure
      </button>
    </>
  )
}

describe('useToast', () => {
  it('shows what it was told to show', async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'info' }))

    expect(await screen.findByText('Search cancelled')).toBeInTheDocument()
  })

  it('reports a failure with its code, in the same words as the inline state', async () => {
    const error = await HttpError.fromResponse(
      Response.json({ code: 'too_many_searches', detail: 'slow down' }, { status: 429 }),
    )
    render(
      <ToastProvider>
        <Probe onFailure={error} />
      </ToastProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'failure' }))

    expect(await screen.findByText('Too many requests')).toBeInTheDocument()
    expect(screen.getByText('too_many_searches')).toBeInTheDocument()
  })

  it('stacks more than one and dismisses the one that was closed', async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'info' }))
    await userEvent.click(screen.getByRole('button', { name: 'info' }))
    expect(await screen.findAllByText('Search cancelled')).toHaveLength(2)

    await userEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0]!)

    expect(await screen.findAllByText('Search cancelled')).toHaveLength(1)
  })

  it('refuses to work outside the provider', () => {
    expect(() => render(<Probe />)).toThrow(/ToastProvider/)
  })
})
