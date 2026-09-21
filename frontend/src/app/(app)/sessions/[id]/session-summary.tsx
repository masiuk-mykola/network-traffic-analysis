import type { components } from '@api/schema'
import { formatByteCount, formatCount, formatDuration, formatTimestamp } from '@lib/format'
import { cn } from '@lib/utils'

type Session = components['schemas']['Session']

const BANDS: Record<string, string> = {
  low: 'text-muted',
  medium: 'text-warning',
  high: 'text-danger',
  critical: 'text-danger',
}

/** What this session is, at a glance: when, where, between whom, how much, how risky. */
export function SessionSummary({ session }: { session: Session }) {
  const bytes = formatByteCount(session.bytes)
  const packets = session.packets

  return (
    <section aria-label="Session summary" className="border-border space-y-4 rounded-lg border p-4">
      <div className="space-y-1">
        <p className="text-lg font-medium">{session.summary}</p>
        <p className="text-muted text-xs">
          {session.protocol} over {session.transport} · decoded by {session.decoder} · session{' '}
          {session.id}
        </p>
      </div>

      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        <Fact label="Started">{formatTimestamp(session.start)}</Fact>
        <Fact label="Lasted">{formatDuration(session.duration_ms)}</Fact>
        <Fact label="Capture point">{session.sensor_id}</Fact>
        <Fact label="From">
          {session.src.ip}:{session.src.port}
          {session.src.country ? ` · ${session.src.country}` : ''}
        </Fact>
        <Fact label="To">
          {session.dst.ip}:{session.dst.port}
          {session.dst.country ? ` · ${session.dst.country}` : ''}
        </Fact>
        <Fact label="Bytes">
          {bytes.total}{' '}
          <span className="text-muted text-xs">
            ↑ {bytes.up} ↓ {bytes.down}
          </span>
        </Fact>
        <Fact label="Packets">
          {formatCount(packets.up + packets.down)}{' '}
          <span className="text-muted text-xs">
            ↑ {formatCount(packets.up)} ↓ {formatCount(packets.down)}
          </span>
        </Fact>
        <Fact label="Risk">
          <span className={cn('font-medium', BANDS[session.risk.band] ?? 'text-muted')}>
            {session.risk.score} ({session.risk.band})
          </span>
        </Fact>
        {session.intel ? (
          <Fact label="Intel">
            {session.intel.score} <span className="text-muted text-xs">{session.intel.source}</span>
          </Fact>
        ) : null}
      </dl>

      {session.risk.reasons.length > 0 ? (
        <div className="space-y-1">
          <p className="text-muted text-xs">Why it scored that way</p>
          <ul className="list-inside list-disc text-sm">
            {session.risk.reasons.map((reason) => (
              <li key={reason.code}>
                {reason.label}
                {reason.mitre ? (
                  <span className="text-muted text-xs"> · {reason.mitre}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-muted text-xs">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  )
}
