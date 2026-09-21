'use client'

import { Check, Copy } from 'lucide-react'
import { useEffect, useState } from 'react'

import { cn } from '@lib/utils'

const SHOWN_MS = 1500

/**
 * Copies the raw value rather than the formatted one — an address, a name or an identifier is
 * usually on its way into another tool. A browser that refuses is not an error worth a screen.
 */
export function CopyButton({
  value,
  label,
  className,
}: {
  value: string
  /** What is being copied, for the control's name: "Copy query name". */
  label: string
  className?: string
}) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), SHOWN_MS)
    return () => clearTimeout(timer)
  }, [copied])

  return (
    <button
      type="button"
      aria-label={copied ? `Copied ${label}` : `Copy ${label}`}
      title={copied ? 'Copied' : `Copy ${label}`}
      onClick={() => {
        void navigator.clipboard
          ?.writeText(value)
          .then(() => setCopied(true))
          .catch(() => undefined)
      }}
      className={cn(
        'text-muted hover:text-foreground focus-visible:ring-ring/60 rounded p-1',
        'focus-visible:ring-2 focus-visible:outline-none',
        className,
      )}
    >
      {copied ? (
        <Check aria-hidden className="text-accent size-3.5" />
      ) : (
        <Copy aria-hidden className="size-3.5" />
      )}
    </button>
  )
}
