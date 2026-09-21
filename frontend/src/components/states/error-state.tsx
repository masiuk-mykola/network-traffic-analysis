'use client'

import { AlertTriangle, LogIn, ShieldAlert } from 'lucide-react'
import { useEffect, useState, type ReactElement } from 'react'

import { describeFailure } from '@api/failure'
import { cn } from '@lib/utils'

type ErrorStateProps = {
  error: unknown
  /** Omit it when there is nothing sensible to re-run; the button only appears when both it and the failure allow. */
  onRetry?: () => void
  variant?: 'page' | 'region'
  className?: string
}

const SECOND_MS = 1000

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
    <button
      type="button"
      onClick={onRetry}
      disabled={waitSeconds > 0}
      className="border-border hover:bg-border rounded border px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-60"
    >
      {waitSeconds > 0 ? `Try again in ${waitSeconds} s` : 'Try again'}
    </button>
  )
}

/** Counts the server-advertised wait down to zero, so the button cannot repeat a refused request. */
function useCountdown(waitMs: number | null): number {
  const [remaining, setRemaining] = useState(() =>
    waitMs !== null && waitMs > 0 ? Math.ceil(waitMs / SECOND_MS) : 0,
  )

  useEffect(() => {
    if (remaining <= 0) return
    const timer = setInterval(() => {
      setRemaining((seconds) => (seconds <= 1 ? 0 : seconds - 1))
    }, SECOND_MS)
    return () => clearInterval(timer)
  }, [remaining])

  return remaining
}

function failureIcon(code: string | null, retryable: boolean): ReactElement {
  const className = 'size-6 text-danger'
  if (code === 'session_revoked') return <LogIn aria-hidden className={className} />
  if (retryable) return <AlertTriangle aria-hidden className={className} />
  return <ShieldAlert aria-hidden className={className} />
}
