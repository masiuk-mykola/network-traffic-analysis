import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FieldCatalogue } from '@lib/search/condition'
import { EMPTY_QUERY } from '@lib/search/query-params'

import { QueryForm } from './query-form'

const replace = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace, refresh: vi.fn() }) }))

const FIELDS: FieldCatalogue = {
  'src.ip': {
    name: 'src.ip',
    label: 'Source IP',
    type: 'ip',
    operators: ['eq', 'cidr', 'exists'],
    example: '10.0.0.1',
  },
  'dst.port': {
    name: 'dst.port',
    label: 'Destination port',
    type: 'port',
    operators: ['eq', 'between'],
    example: '443',
  },
  protocol: {
    name: 'protocol',
    label: 'Protocol',
    type: 'enum',
    operators: ['eq'],
    enum_name: 'protocol',
    example: 'dns',
  },
}

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
  ],
}

const ENUM = {
  name: 'protocol',
  values: [
    { value: 'dns', label: 'DNS' },
    { value: 'tls', label: 'TLS' },
  ],
}

function renderForm() {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      calls.push(url)
      if (url.includes('sensors')) return Response.json(SENSORS, { status: 200 })
      if (url.includes('meta/enums/')) return Response.json(ENUM, { status: 200 })
      return Response.json({ items: Object.values(FIELDS) }, { status: 200 })
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <QueryForm initial={EMPTY_QUERY} fields={FIELDS} readable={['hq-core', 'harbor-branch']} />
    </QueryClientProvider>,
  )
  return calls
}

async function addCondition() {
  await userEvent.click(await screen.findByRole('button', { name: /add condition/i }))
}

async function choose(label: string, option: string | RegExp) {
  await userEvent.click(screen.getByRole('combobox', { name: label }))
  await userEvent.click(await screen.findByRole('option', { name: option }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the condition builder', () => {
  it('offers only the comparisons the chosen field allows', async () => {
    renderForm()
    await addCondition()
    await choose('Field', 'Source IP')

    await userEvent.click(screen.getByRole('combobox', { name: 'Comparison' }))

    expect(await screen.findByRole('option', { name: 'is inside' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'between' })).not.toBeInTheDocument()
  })

  it('clears a comparison the new field does not allow', async () => {
    renderForm()
    await addCondition()
    await choose('Field', 'Destination port')
    await choose('Comparison', 'between')
    await choose('Field', 'Source IP')

    expect(screen.getByRole('combobox', { name: 'Comparison' })).toHaveTextContent('Comparison')
  })

  it('asks for values from the published set when the field is closed', async () => {
    renderForm()
    await addCondition()
    await choose('Field', 'Protocol')
    await choose('Comparison', 'is')

    await userEvent.click(await screen.findByRole('combobox', { name: 'Value' }))

    expect(await screen.findByRole('option', { name: 'DNS' })).toBeInTheDocument()
  })

  it('asks for two bounds for a range, and blocks until both are there', async () => {
    renderForm()
    await addCondition()
    await choose('Field', 'Destination port')
    await choose('Comparison', 'between')

    expect(screen.getByRole('textbox', { name: 'From' })).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'From' }), '1024')

    expect(await screen.findByText('A range needs two values.')).toBeInTheDocument()
  })

  it('asks for nothing when the comparison takes no value', async () => {
    renderForm()
    await addCondition()
    await choose('Field', 'Source IP')
    await choose('Comparison', 'is present')

    expect(screen.queryByRole('textbox', { name: 'Value' })).not.toBeInTheDocument()
  })

  it('blocks the search while a condition is unfinished', async () => {
    renderForm()
    await screen.findByText('HQ Core')
    await userEvent.click(screen.getAllByRole('checkbox')[0]!)
    await addCondition()

    expect(screen.getByRole('button', { name: 'Run search' })).toBeDisabled()
    expect(screen.getByText(/a condition is unfinished/i)).toBeInTheDocument()
  })

  it('asks the server once for a set used by two conditions', async () => {
    const calls = renderForm()
    await addCondition()
    await choose('Field', 'Protocol')
    await choose('Comparison', 'is')
    await addCondition()
    const fieldPickers = screen.getAllByRole('combobox', { name: 'Field' })
    await userEvent.click(fieldPickers[1]!)
    await userEvent.click(await screen.findByRole('option', { name: 'Protocol' }))

    await waitFor(() =>
      expect(calls.filter((url) => url.includes('meta/enums/protocol'))).toHaveLength(1),
    )
  })

  it('does not ask for the field catalogue the server already read', async () => {
    const calls = renderForm()
    await screen.findByText('HQ Core')

    expect(calls.filter((url) => url.includes('meta/fields'))).toHaveLength(0)
  })
})
