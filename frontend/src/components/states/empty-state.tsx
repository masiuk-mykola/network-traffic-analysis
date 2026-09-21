import { Inbox } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@lib/utils'

type EmptyStateProps = {
  title: string
  description?: string
  /** A way back to whatever produced the emptiness — usually the filters. */
  action?: ReactNode
  icon?: LucideIcon
  variant?: 'page' | 'region'
  className?: string
}

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
  variant = 'region',
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 px-6 text-center',
        variant === 'page' ? 'min-h-[60vh]' : 'min-h-40 py-8',
        className,
      )}
    >
      <Icon aria-hidden className="text-muted size-6" />
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description ? <p className="text-muted max-w-prose text-sm">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}
