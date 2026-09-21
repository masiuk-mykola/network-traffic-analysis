import type { InputHTMLAttributes } from 'react'

import { cn } from '@lib/utils'

/** One input everywhere: hairline border, a hover that acknowledges the pointer, a real focus ring. */
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'border-border bg-surface/70 text-foreground placeholder:text-muted/70 h-10 w-full rounded-md border px-3 text-sm',
        'transition-[border-color,box-shadow,background-color] duration-150 ease-out',
        'hover:border-muted/60',
        'focus-visible:border-accent focus-visible:ring-ring/40 focus-visible:ring-2 focus-visible:outline-none',
        'aria-[invalid=true]:border-danger aria-[invalid=true]:focus-visible:ring-danger/30',
        'disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...props}
    />
  )
}
