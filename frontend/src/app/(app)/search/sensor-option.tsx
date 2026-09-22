'use client'

import { Lock } from 'lucide-react'
import { useId } from 'react'

import { formatDuration } from '@lib/format'
import type { Sensor } from '@lib/search/use-sensors'
import { cn } from '@lib/utils'
import { Checkbox } from '@/components/form/checkbox'

type SensorOptionProps = {
  sensor: Sensor
  checked: boolean
  /** The account cannot read this point. It is shown so the gap is visible, but it cannot be used. */
  locked?: boolean
  disabled: boolean
  onToggle: (checked: boolean) => void
}

export function SensorOption({ sensor, checked, locked, disabled, onToggle }: SensorOptionProps) {
  const id = useId()
  const noteId = `${id}-note`
  const behind = sensor.status === 'lagging' || (sensor.lag_seconds ?? 0) > 60

  return (
    <li
      className={cn(
        'border-border flex items-center gap-3 border-b px-3 py-2.5 last:border-b-0',
        disabled && 'opacity-50',
      )}
    >
      <Checkbox
        id={id}
        checked={checked}
        disabled={disabled}
        aria-describedby={locked ? noteId : undefined}
        onCheckedChange={onToggle}
      />
      <label
        htmlFor={id}
        className={cn(
          'flex flex-1 items-baseline gap-2',
          locked ? 'cursor-not-allowed' : 'cursor-pointer',
        )}
      >
        {locked ? <Lock aria-hidden className="size-3.5 self-center" /> : null}
        <span className="text-sm font-medium">{sensor.name}</span>
        <span className="text-muted text-xs">{sensor.site}</span>
      </label>
      <Marker behind={behind} locked={locked} noteId={noteId} sensor={sensor} />
    </li>
  )
}

function Marker({
  behind,
  locked,
  noteId,
  sensor,
}: {
  behind: boolean
  locked?: boolean
  noteId: string
  sensor: Sensor
}) {
  // What the point is doing matters only where it can be searched; where it cannot, that is the
  // one thing worth saying about it.
  if (locked) {
    return (
      <span
        id={noteId}
        className="border-border text-muted rounded-full border px-2 py-0.5 font-mono text-[0.65rem] tracking-wider uppercase"
      >
        No access
      </span>
    )
  }

  if (behind) {
    return (
      <span className="border-danger/50 text-danger rounded-full border px-2 py-0.5 font-mono text-[0.65rem] tracking-wider uppercase">
        behind {formatDuration((sensor.lag_seconds ?? 0) * 1000)}
      </span>
    )
  }

  return (
    <span className="text-muted font-mono text-[0.65rem] tracking-wider uppercase">
      {sensor.status}
    </span>
  )
}
