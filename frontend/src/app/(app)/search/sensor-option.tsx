'use client'

import { useId } from 'react'

import { formatDuration } from '@lib/format'
import type { Sensor } from '@lib/search/use-sensors'
import { cn } from '@lib/utils'
import { Checkbox } from '@/components/form/checkbox'

type SensorOptionProps = {
  sensor: Sensor
  checked: boolean
  disabled: boolean
  onToggle: (checked: boolean) => void
}

export function SensorOption({ sensor, checked, disabled, onToggle }: SensorOptionProps) {
  const id = useId()
  const behind = sensor.status === 'lagging' || (sensor.lag_seconds ?? 0) > 60

  return (
    <li
      className={cn(
        'border-border flex items-center gap-3 border-b px-3 py-2.5 last:border-b-0',
        disabled && 'opacity-50',
      )}
    >
      <Checkbox id={id} checked={checked} disabled={disabled} onCheckedChange={onToggle} />
      <label htmlFor={id} className="flex flex-1 cursor-pointer items-baseline gap-2">
        <span className="text-sm font-medium">{sensor.name}</span>
        <span className="text-muted text-xs">{sensor.site}</span>
      </label>
      {behind ? (
        <span className="border-danger/50 text-danger rounded-full border px-2 py-0.5 font-mono text-[0.65rem] tracking-wider uppercase">
          behind {formatDuration((sensor.lag_seconds ?? 0) * 1000)}
        </span>
      ) : (
        <span className="text-muted font-mono text-[0.65rem] tracking-wider uppercase">
          {sensor.status}
        </span>
      )}
    </li>
  )
}
