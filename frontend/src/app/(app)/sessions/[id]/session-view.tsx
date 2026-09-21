'use client'

import { ArrowLeft, FileWarning, ShieldAlert } from 'lucide-react'
import { useRouter } from 'next/navigation'

import type { ReactNode } from 'react'

import type { components } from '@api/schema'
import { formatBytes, formatTimestamp } from '@lib/format'
import { isNotFound, type SessionStatus } from '@lib/session/session-state'
import { useProtocolSchema } from '@lib/session/use-protocol-schema'
import { readDnsExchange } from '@lib/session/dns'
import { useSession } from '@lib/session/use-session'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

import { DnsExchange } from './dns-exchange'
import { SessionSummary } from './session-summary'
import { Transaction } from './transaction'

type Session = components['schemas']['Session']

export function SessionView({
  sessionId,
  initialStatus,
}: {
  sessionId: string
  /** What the page read on the server, so the browser inherits the answer. */
  initialStatus?: SessionStatus
}) {
  const router = useRouter()
  const session = useSession(sessionId, { sessionId, status: initialStatus })
  const protocol = session.data && !isNotFound(session.data) ? session.data.protocol : null
  const schema = useProtocolSchema(protocol)

  const back = (
    <Button variant="ghost" size="sm" onClick={() => router.back()}>
      <ArrowLeft aria-hidden className="size-4" />
      Back to results
    </Button>
  )

  if (session.isPending) return <LoadingState label="Loading session" />
  if (session.isError) {
    return <ErrorState error={session.error} onRetry={() => void session.refetch()} />
  }

  if (isNotFound(session.data)) {
    return (
      <EmptyState
        variant="page"
        title="No such session"
        description="The capture has no session with this id, or this account cannot read it."
        action={back}
      />
    )
  }

  const found = session.data
  // Written properly for one protocol; every other one has the generic view below, and so does this
  // one — specialising must not hide a field the layout does not know about.
  const dns = readDnsExchange(found.decoded)

  return (
    <div className="space-y-6">
      <div>{back}</div>

      <SessionSummary session={found} />

      {dns ? <DnsExchange exchange={dns} risk={found.risk} detections={found.detections} /> : null}

      <Transaction
        decoded={found.decoded}
        fields={schema.data}
        describing={schema.isPending || schema.isError}
      />

      <section aria-label="What else was recorded" className="space-y-3">
        <Detections detections={found.detections} />
        <Files files={found.files} />
        <Capture pcap={found.pcap} />
      </section>
    </div>
  )
}

function Detections({ detections }: { detections: Session['detections'] }) {
  if (detections.length === 0) {
    return <Fact>No rule fired on this session.</Fact>
  }

  return (
    <ul className="space-y-2">
      {detections.map((detection) => (
        <li
          key={detection.rule_id}
          className="border-border flex items-start gap-2 rounded-lg border p-3 text-sm"
        >
          <ShieldAlert aria-hidden className="text-warning mt-0.5 size-4 shrink-0" />
          <span>
            {detection.rule}{' '}
            <span className="text-muted text-xs">
              {detection.severity} · {detection.mitre.technique_id} {detection.mitre.name}
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Files({ files }: { files: Session['files'] }) {
  if (files.length === 0) return <Fact>No files were carved out of it.</Fact>

  return (
    <ul className="space-y-2">
      {files.map((file) => (
        <li
          key={file.id}
          className="border-border flex items-start gap-2 rounded-lg border p-3 text-sm"
        >
          <FileWarning aria-hidden className="text-muted mt-0.5 size-4 shrink-0" />
          <span className="break-all">
            {file.name}{' '}
            <span className="text-muted text-xs">
              {file.mime} · {formatBytes(file.size)} · {file.source}
              {file.purged ? ' · purged' : ''}
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Capture({ pcap }: { pcap: Session['pcap'] }) {
  if (pcap.available) return <Fact>The raw capture is still held for this session.</Fact>

  return (
    <Fact>
      The raw capture is gone
      {pcap.reason ? ` (${pcap.reason})` : ''}
      {pcap.expired_at ? `, expired ${formatTimestamp(pcap.expired_at)}` : ''}.
    </Fact>
  )
}

function Fact({ children }: { children: ReactNode }) {
  return <p className="text-muted text-sm">{children}</p>
}
