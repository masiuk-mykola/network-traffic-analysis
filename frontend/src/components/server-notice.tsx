'use client'

import { X } from 'lucide-react'
import { useState } from 'react'

import { useHealth } from '@lib/health/use-health'
import { Button } from '@/components/ui'

/**
 * What the server says about its own condition, once, above every screen.
 *
 * It is the server's sentence, not ours, and it blocks nothing: a degraded index makes searches slow
 * or likely to fail, which is worth knowing while reading a slow screen. Dismissing it is per
 * condition, so a different part going unwell says so again.
 */
export function ServerNotice() {
  const health = useHealth()
  const [dismissed, setDismissed] = useState<string | null>(null)

  const degraded = health.data ?? []
  if (degraded.length === 0) return null

  const condition = degraded.map((part) => part.name).join(',')
  if (dismissed === condition) return null

  return (
    <div
      role="status"
      aria-label="Server condition"
      className="border-warning/40 bg-warning/5 flex items-start gap-3 border-b px-6 py-2 text-sm"
    >
      <p className="flex-1">
        {degraded.map((part) => (
          <span key={part.name} className="mr-3">
            <span className="font-mono text-xs">{part.name}</span>{' '}
            {part.detail ?? 'is degraded, the server says.'}
          </span>
        ))}
      </p>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Dismiss"
        onClick={() => setDismissed(condition)}
      >
        <X aria-hidden className="size-4" />
      </Button>
    </div>
  )
}
