import { ShieldAlert } from 'lucide-react'

import type { components } from '@api/schema'
import { EMPTY, formatDuration } from '@lib/format'
import type { DnsExchange as Exchange, DnsRecord } from '@lib/session/dns'
import { cn } from '@lib/utils'
import { CopyButton } from '@/components/ui'

type Session = components['schemas']['Session']

const SECOND_MS = 1000

/**
 * A DNS session as the exchange it is: what was asked on one side, what came back on the other,
 * with the records beneath. What is anomalous about it is what the server says is anomalous — the
 * reasons behind its risk, and any rule it reports; nothing here judges a name for itself.
 */
export function DnsExchange({
  exchange,
  risk,
  detections,
}: {
  exchange: Exchange
  risk: Session['risk']
  detections: Session['detections']
}) {
  const records = [
    { title: 'Answers', items: exchange.answers },
    { title: 'Authority', items: exchange.authority },
    { title: 'Additional', items: exchange.additional },
  ].filter((set) => set.items.length > 0)

  return (
    <section aria-label="DNS exchange" className="space-y-4">
      <div className="grid gap-px overflow-hidden rounded-lg border-0 sm:grid-cols-2">
        <Half title="Question">
          {exchange.query ? (
            <>
              <Line label="Name" value={exchange.query.name} copyable emphasis />
              <Line label="Type" value={exchange.query.type} />
              <Line label="Class" value={exchange.query.class ?? EMPTY} />
            </>
          ) : (
            <p className="text-muted text-sm">The decoder recorded no question.</p>
          )}
        </Half>

        <Half title="Response">
          <Line
            label="Code"
            value={exchange.responseCode.name || EMPTY}
            emphasis
            tone={toneFor(exchange.responseCode.code)}
          />
          <Line label="Flags" value={exchange.flags.join(', ') || 'none set'} />
          <Line
            label="Transaction"
            value={exchange.transactionId ?? EMPTY}
            copyable={exchange.transactionId !== null}
          />
        </Half>
      </div>

      {risk.reasons.length > 0 || detections.length > 0 ? (
        <ul aria-label="What the server flagged" className="space-y-2">
          {risk.reasons.map((reason) => (
            <Flag key={reason.code} note={reason.mitre}>
              {reason.label}
            </Flag>
          ))}
          {detections.map((detection) => (
            <Flag
              key={detection.rule_id}
              note={`${detection.severity} · ${detection.mitre.technique_id} ${detection.mitre.name}`}
            >
              {detection.rule}
            </Flag>
          ))}
        </ul>
      ) : null}

      {records.length > 0 ? (
        <div className="space-y-3">
          {records.map((set) => (
            <RecordSet key={set.title} title={set.title} items={set.items} />
          ))}
        </div>
      ) : (
        <p className="text-muted text-sm">No records came back with this answer.</p>
      )}
    </section>
  )
}

function Half({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-border bg-surface/40 space-y-2 border p-4">
      <p className="text-muted text-xs tracking-wide uppercase">{title}</p>
      <dl className="space-y-1.5">{children}</dl>
    </div>
  )
}

function Line({
  label,
  value,
  copyable,
  emphasis,
  tone,
}: {
  label: string
  value: string
  copyable?: boolean
  emphasis?: boolean
  tone?: string
}) {
  return (
    <div className="grid grid-cols-[6rem_1fr] items-start gap-2">
      <dt className="text-muted text-xs">{label}</dt>
      <dd className="flex items-start gap-1 text-sm break-all">
        <span className={cn(emphasis && 'font-medium', tone)}>{value}</span>
        {copyable ? <CopyButton value={value} label={label.toLowerCase()} /> : null}
      </dd>
    </div>
  )
}

function RecordSet({ title, items }: { title: string; items: DnsRecord[] }) {
  return (
    <div className="space-y-1">
      <p className="text-muted text-xs tracking-wide uppercase">{title}</p>
      <ul className="border-border divide-border divide-y rounded-lg border">
        {items.map((record, index) => (
          <li key={`${record.name}-${record.type}-${index}`} className="px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium">{record.type || EMPTY}</span>
              <span className="break-all">{record.name || EMPTY}</span>
              {record.ttl === null ? null : (
                <span className="text-muted text-xs">
                  lives {formatDuration(record.ttl * SECOND_MS)}
                </span>
              )}
            </div>
            {record.data ? (
              <p className="text-muted mt-1 flex items-start gap-1 break-all">
                {record.data}
                <CopyButton value={record.data} label="record data" />
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Flag({ children, note }: { children: React.ReactNode; note?: string }) {
  return (
    <li className="border-warning/40 bg-warning/5 flex items-start gap-2 rounded-lg border p-3 text-sm">
      <ShieldAlert aria-hidden className="text-warning mt-0.5 size-4 shrink-0" />
      <span>
        {children}
        {note ? <span className="text-muted ml-2 text-xs">{note}</span> : null}
      </span>
    </li>
  )
}

/** A refusal or a failure reads differently from an ordinary answer. */
function toneFor(code: number | null): string | undefined {
  if (code === null || code === 0) return undefined
  return 'text-warning'
}
