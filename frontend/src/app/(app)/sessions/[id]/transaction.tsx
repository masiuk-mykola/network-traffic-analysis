'use client'

import { tableFeatures, useTable, type ColumnDef as TableColumnDef } from '@tanstack/react-table'
import { useMemo } from 'react'

import { EMPTY, formatByColumnType, isRedacted } from '@lib/format'
import { splitDecoded } from '@lib/session/described'
import { cn } from '@lib/utils'
import type { components } from '@api/schema'
import { EmptyState } from '@/components/states'

type SchemaField = components['schemas']['SchemaField']

const features = tableFeatures({})

/** One row of the transaction: what the server calls it, and what it decoded. */
type FieldRow = {
  path: string
  label: string
  note: string | undefined
  values: string[]
  monospace: boolean
}

/**
 * The decoded transaction: the server's own labels, in the server's own order, and beneath them
 * everything it decoded but never described — a session from an older decoder is mostly that.
 */
export function Transaction({
  decoded,
  fields,
  describing,
}: {
  decoded: unknown
  fields: SchemaField[] | undefined
  /** True while the description is still being read; the values are shown either way. */
  describing: boolean
}) {
  const { described, undescribed } = splitDecoded(decoded, fields ?? [])

  const describedRows = useMemo<FieldRow[]>(
    () =>
      described.map((field) => ({
        path: field.path,
        label: field.title,
        note: noteFor(field.sensitive, field.unit, field.values),
        values: field.values.map((value) => formatByColumnType(field.type, value)),
        monospace: false,
      })),
    [described],
  )

  const undescribedRows = useMemo<FieldRow[]>(
    () =>
      undescribed.map((entry) => ({
        path: entry.path,
        label: entry.path,
        note: undefined,
        values: [formatByColumnType('text', entry.value)],
        monospace: true,
      })),
    [undescribed],
  )

  if (described.length === 0 && undescribed.length === 0) {
    return (
      <EmptyState
        title="Nothing was decoded"
        description="This session has no transaction to show — the decoder recorded only what is in the summary."
      />
    )
  }

  return (
    <div className="space-y-6">
      {described.length > 0 ? (
        <section aria-label="Transaction" className="border-border rounded-lg border">
          <FieldTable caption="Transaction" rows={describedRows} />
        </section>
      ) : null}

      {undescribed.length > 0 ? (
        <section aria-label="Not described by the schema" className="space-y-2">
          <p className="text-muted text-xs">
            {describing
              ? 'Still reading how this protocol is described; these are the decoded values.'
              : 'Decoded, but not part of the published description of this protocol.'}
          </p>
          <div className="border-border rounded-lg border">
            <FieldTable caption="Not described by the schema" rows={undescribedRows} />
          </div>
        </section>
      ) : null}
    </div>
  )
}

/** What the label carries beside itself: why a value is missing, or what unit it is in. */
function noteFor(
  sensitive: boolean,
  unit: string | undefined,
  values: unknown[],
): string | undefined {
  if (values.some(isRedacted)) return 'withheld'
  if (sensitive) return 'sensitive'
  return unit
}

/**
 * Label and value, as a two-column table. The label is the row's own header (`th scope="row"`), so
 * a screen reader still reads "label: value" the way the description list it replaced did.
 */
function FieldTable({ caption, rows }: { caption: string; rows: FieldRow[] }) {
  const columns = useMemo<TableColumnDef<typeof features, FieldRow>[]>(
    () => [
      {
        id: 'label',
        header: 'Field',
        cell: ({ row }) => (
          <>
            {row.original.label}
            {row.original.note ? (
              <span className="text-warning ml-2 text-xs">{row.original.note}</span>
            ) : null}
          </>
        ),
      },
      {
        id: 'value',
        header: 'Value',
        cell: ({ row }) =>
          row.original.values.length === 0
            ? EMPTY
            : row.original.values.map((value, index) => <p key={index}>{value}</p>),
      },
    ],
    [],
  )

  const table = useTable({ features, columns, data: rows })

  return (
    // Fixed layout, so a value with no place to break (a hash, a body preview) wraps inside its
    // column instead of widening the table past its frame.
    <table className="w-full table-fixed text-left">
      <caption className="sr-only">{caption}</caption>
      <colgroup>
        <col className="w-32 sm:w-56" />
        <col />
      </colgroup>
      <thead className="sr-only">
        {table.getHeaderGroups().map((group) => (
          <tr key={group.id}>
            {group.headers.map((header) => (
              <th key={header.id} scope="col">
                <table.FlexRender header={header} />
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody className="divide-border divide-y">
        {table.getRowModel().rows.map((row) => {
          const [label, value] = row.getAllCells()
          if (!label || !value) return null
          return (
            <tr key={row.id} className="align-top">
              <th
                scope="row"
                className={cn(
                  'px-4 py-2 font-normal break-words',
                  row.original.monospace ? 'text-muted font-mono text-xs' : 'text-muted text-sm',
                )}
              >
                <table.FlexRender cell={label} />
              </th>
              <td className="space-y-0.5 px-4 py-2 text-sm [overflow-wrap:anywhere]">
                <table.FlexRender cell={value} />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
