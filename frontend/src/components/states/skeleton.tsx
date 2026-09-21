import { cn } from '@lib/utils'

/** A placeholder that holds the shape of the content, so nothing jumps when it arrives. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('bg-border animate-pulse rounded', className)} />
}
