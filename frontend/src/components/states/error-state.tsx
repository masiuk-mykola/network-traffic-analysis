'use client'

import { AlertTriangle, Loader2, LogIn, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState, type ReactElement } from 'react'

import { describeFailure } from '@api/failure'
import { Button } from '@/components/ui'
import { useCountdown } from '@lib/use-countdown'
import { cn } from '@lib/utils'

type ErrorStateProps = {
  error: unknown
  /** Omit it when there is nothing sensible to re-run; the button only appears when both it and the failure allow. */
  onRetry?: () => void
  /** True while the read is being attempted again, so a retry is never silent. */
  retrying?: boolean
  variant?: 'page' | 'region'
  className?: string
}

export function ErrorState({
  error,
  onRetry,
  retrying = false,
  variant = 'region',
  className,
}: ErrorStateProps) {
  const failure = describeFailure(error)
  const showRetry = failure.retryable && onRetry !== undefined
  const attempt = useAttempt(retrying)

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
        // Keyed by the failure so a later refusal restarts the wait instead of inheriting a
        // countdown that already reached zero. A dropped connection carries no identity, so the
        // attempt itself is the key — otherwise two of them in a row would share one button.
        <RetryButton
          key={failure.id ?? `attempt-${attempt}`}
          waitMs={failure.retryAfterMs}
          retrying={retrying}
          onRetry={onRetry}
        />
      ) : null}
      {failure.code ? <p className="text-muted text-xs">{failure.code}</p> : null}
    </div>
  )
}

/** Counts the attempts this state has seen, so a failure with no identity of its own still has one. */
function useAttempt(retrying: boolean): number {
  const [attempt, setAttempt] = useState(0)
  const wasRetrying = useRef(retrying)

  useEffect(() => {
    if (wasRetrying.current && !retrying) setAttempt((count) => count + 1)
    wasRetrying.current = retrying
  }, [retrying])

  return attempt
}

function RetryButton({
  waitMs,
  retrying,
  onRetry,
}: {
  waitMs: number | null
  retrying: boolean
  onRetry: () => void
}) {
  const waitSeconds = useCountdown(waitMs)

  return (
    <Button variant="secondary" size="sm" onClick={onRetry} disabled={retrying || waitSeconds > 0}>
      {retrying ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
      {retryLabel(retrying, waitSeconds)}
    </Button>
  )
}

function retryLabel(retrying: boolean, waitSeconds: number): string {
  if (retrying) return 'Trying again'
  if (waitSeconds > 0) return `Try again in ${waitSeconds} s`
  return 'Try again'
}

function failureIcon(code: string | null, retryable: boolean): ReactElement {
  const className = 'size-6 text-danger'
  if (code === 'session_revoked') return <LogIn aria-hidden className={className} />
  if (retryable) return <AlertTriangle aria-hidden className={className} />
  return <ShieldAlert aria-hidden className={className} />
}
