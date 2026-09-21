import { EMPTY, formatByColumnType } from '@lib/format'
import { splitDecoded } from '@lib/session/described'
import type { components } from '@api/schema'
import { EmptyState } from '@/components/states'

type SchemaField = components['schemas']['SchemaField']

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
          <dl className="divide-border divide-y">
            {described.map((field) => (
              <Row
                key={field.path}
                label={field.title}
                note={field.sensitive ? 'sensitive' : field.unit}
                values={field.values.map((value) => formatByColumnType(field.type, value))}
              />
            ))}
          </dl>
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
            <dl className="divide-border divide-y">
              {undescribed.map((entry) => (
                <Row
                  key={entry.path}
                  label={entry.path}
                  values={[formatByColumnType('text', entry.value)]}
                  monospace
                />
              ))}
            </dl>
          </div>
        </section>
      ) : null}
    </div>
  )
}

function Row({
  label,
  note,
  values,
  monospace,
}: {
  label: string
  note?: string | undefined
  values: string[]
  monospace?: boolean
}) {
  return (
    <div className="grid gap-1 px-4 py-2 sm:grid-cols-[14rem_1fr] sm:gap-4">
      <dt className={monospace ? 'text-muted font-mono text-xs' : 'text-muted text-sm'}>
        {label}
        {note ? <span className="text-warning ml-2 text-xs">{note}</span> : null}
      </dt>
      <dd className="space-y-0.5 text-sm break-words">
        {values.length === 0 ? EMPTY : values.map((value, index) => <p key={index}>{value}</p>)}
      </dd>
    </div>
  )
}
