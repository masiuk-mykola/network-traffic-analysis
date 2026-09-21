import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CopyButton } from './copy-button'

function stubClipboard(writeText: (value: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CopyButton', () => {
  it('copies the value it was given, not what the screen shows', async () => {
    const copied: string[] = []
    stubClipboard(async (value) => void copied.push(value))

    render(<CopyButton value="49d5ef90.video.example.net" label="query name" />)
    await userEvent.click(screen.getByRole('button', { name: /copy query name/i }))

    expect(copied).toEqual(['49d5ef90.video.example.net'])
    expect(await screen.findByRole('button', { name: /copied/i })).toBeVisible()
  })

  it('stays out of the way when the browser refuses', async () => {
    stubClipboard(async () => {
      throw new Error('denied')
    })

    render(<CopyButton value="10.20.0.7" label="answer" />)
    await userEvent.click(screen.getByRole('button', { name: /copy answer/i }))

    await waitFor(() => expect(screen.getByRole('button', { name: /copy answer/i })).toBeVisible())
  })

  it('does nothing at all where there is no clipboard', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })

    render(<CopyButton value="10.20.0.7" label="answer" />)
    await userEvent.click(screen.getByRole('button', { name: /copy answer/i }))

    expect(screen.getByRole('button', { name: /copy answer/i })).toBeVisible()
  })
})
