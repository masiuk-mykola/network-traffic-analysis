import type { ButtonHTMLAttributes } from 'react'

import { cn } from '@lib/utils'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md'
}

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap ' +
  'transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out ' +
  'focus-visible:ring-ring/60 focus-visible:ring-2 focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-background focus-visible:outline-none ' +
  'active:translate-y-px disabled:pointer-events-none disabled:opacity-50'

const VARIANTS = {
  primary:
    'bg-accent text-accent-contrast shadow-sm hover:brightness-110 active:brightness-95 ' +
    'disabled:shadow-none',
  secondary:
    'border-border bg-surface text-foreground border hover:border-accent/60 ' +
    'hover:bg-accent/5 active:bg-accent/10',
  ghost: 'text-muted hover:text-foreground hover:bg-foreground/5 active:bg-foreground/10',
} as const

const SIZES = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
} as const

export function Button({
  variant = 'primary',
  size = 'md',
  className,
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...props}
    />
  )
}
