'use client'

import { AlertTriangle, LogIn, ShieldAlert } from 'lucide-react'
import { type ReactElement } from 'react'

import { describeFailure } from '@api/failure'
import { Button } from '@/components/ui'
import { useCountdown } from '@lib/use-countdown'
import { cn } from '@lib/utils'

type ErrorStateProps = {
  error: unknown
  /** Omit it when there is nothing sensible to re-run; the button only appears when both it and the failure allow. */
  onRetry?: () => void
  variant?: 'page' | 'region'
  className?: string
}

export function ErrorState({ error, onRetry, variant = 'region', className }: ErrorStateProps) {
  const failure = describeFailure(error)
  const showRetry = failure.retryable && onRetry !== undefined

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-3 px-6 text-center',
        variant === 'page' ? 'min-h-[60vh]' : 'min-h-40 py-8',
        className,
      )}
    >
      {failureIcon(failure.code, failure.retryable)}
      <div className="space-y-1">
        <p className="font-medium">{failure.title}</p>
        <p className="text-muted max-w-prose text-sm">{failure.detail}</p>
      </div>
      {showRetry ? (
        // Keyed by the failure: a later refusal restarts the wait instead of inheriting
        // a countdown that already reached zero.
        <RetryButton key={failure.id ?? 'once'} waitMs={failure.retryAfterMs} onRetry={onRetry} />
      ) : null}
      {failure.code ? <p className="text-muted text-xs">{failure.code}</p> : null}
    </div>
  )
}

function RetryButton({ waitMs, onRetry }: { waitMs: number | null; onRetry: () => void }) {
  const waitSeconds = useCountdown(waitMs)

  return (
    <Button variant="secondary" size="sm" onClick={onRetry} disabled={waitSeconds > 0}>
      {waitSeconds > 0 ? `Try again in ${waitSeconds} s` : 'Try again'}
    </Button>
  )
}

function failureIcon(code: string | null, retryable: boolean): ReactElement {
  const className = 'size-6 text-danger'
  if (code === 'session_revoked') return <LogIn aria-hidden className={className} />
  if (retryable) return <AlertTriangle aria-hidden className={className} />
  return <ShieldAlert aria-hidden className={className} />
}
