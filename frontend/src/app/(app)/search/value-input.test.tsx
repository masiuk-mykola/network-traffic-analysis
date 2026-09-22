import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FieldDef } from '@lib/search/condition'

import { ValueInput } from './value-input'

const CLOSED: FieldDef = {
  name: 'protocol',
  label: 'Protocol',
  type: 'enum',
  operators: ['eq'],
  enum_name: 'protocol',
  example: 'dns',
} as FieldDef

const INLINE: FieldDef = {
  name: 'transport',
  label: 'Transport',
  type: 'enum',
  operators: ['eq'],
  enum: ['tcp', 'udp'],
  example: 'tcp',
} as FieldDef

function renderInput(field: FieldDef, reply: () => Promise<Response>) {
  const asked: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input))
      return reply()
    }),
  )
  const onChange = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ValueInput field={field} op="eq" values={[]} onChange={onChange} />
    </QueryClientProvider>,
  )
  return { asked, onChange }
}

const values = async () => Response.json({ values: [{ value: 'dns', label: 'DNS' }] })
const refused = async () => Response.json({ code: 'unavailable', detail: 'busy' }, { status: 503 })

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ValueInput, for a field whose values the server publishes', () => {
  it('waits for the list before offering a choice', async () => {
    renderInput(CLOSED, () => new Promise<Response>(() => {}))

    expect(screen.getByRole('combobox', { name: 'Value' })).toBeDisabled()
  })

  it('offers the published values once they arrive', async () => {
    renderInput(CLOSED, values)

    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Value' })).toBeEnabled())
  })

  it('says the list could not be read, and offers to read it again', async () => {
    const { asked } = renderInput(CLOSED, refused)

    const retry = await screen.findByRole('button', { name: /try(ing)? again/i })
    expect(screen.getByText(/could not be read/i)).toBeVisible()

    await userEvent.click(retry)

    await waitFor(() => expect(asked.length).toBeGreaterThan(1))
  })

  it('still lets the value be typed when the list cannot be read', async () => {
    const { onChange } = renderInput(CLOSED, refused)

    const box = await screen.findByRole('textbox', { name: 'Value' })
    // The control is controlled by its caller, so each keystroke is reported on its own.
    await userEvent.type(box, 'd')

    expect(onChange).toHaveBeenCalledWith(['d'])
  })

  it('asks for nothing at all when the field carries its values inline', () => {
    const { asked } = renderInput(INLINE, values)

    expect(asked).toEqual([])
    expect(screen.getByRole('combobox', { name: 'Value' })).toBeEnabled()
  })
})
