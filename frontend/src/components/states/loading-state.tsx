import { Loader2 } from 'lucide-react'

import { cn } from '@lib/utils'

type LoadingStateProps = {
  /** What is being loaded, e.g. "Loading sessions". Announced, so keep it stable. */
  label?: string
  variant?: 'page' | 'region'
  className?: string
}

export function LoadingState({
  label = 'Loading',
  variant = 'region',
  className,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'text-muted flex flex-col items-center justify-center gap-3',
        variant === 'page' ? 'min-h-[60vh]' : 'min-h-40 py-8',
        className,
      )}
    >
      <Loader2 aria-hidden className="size-5 animate-spin" />
      <p className="text-sm">{label}</p>
    </div>
  )
}
