'use client'

import { MAX_SENSORS } from '@lib/search/query-params'
import type { Sensor } from '@lib/search/use-sensors'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'

import { SensorOption } from './sensor-option'

/**
 * The capture points, with their own three states.
 *
 * They live in their own component because a refused read must not take the screen with it: the
 * window, the conditions and the run control are still worth having on screen, and the run control
 * already refuses a query with no point chosen.
 */
export function SensorList({
  items,
  chosen,
  isPending,
  error,
  retrying,
  onRetry,
  onToggle,
}: {
  items: Sensor[]
  chosen: string[]
  isPending: boolean
  error: unknown
  retrying: boolean
  onRetry: () => void
  onToggle: (id: string, next: boolean) => void
}) {
  const atLimit = chosen.length >= MAX_SENSORS

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">Capture points</legend>
      <p className="text-muted text-xs">
        Between one and {MAX_SENSORS}. A point that is behind has not reported its most recent
        traffic yet.
      </p>
      <Body
        items={items}
        chosen={chosen}
        atLimit={atLimit}
        isPending={isPending}
        error={error}
        retrying={retrying}
        onRetry={onRetry}
        onToggle={onToggle}
      />
    </fieldset>
  )
}

function Body({
  items,
  chosen,
  atLimit,
  isPending,
  error,
  retrying,
  onRetry,
  onToggle,
}: {
  items: Sensor[]
  chosen: string[]
  atLimit: boolean
  isPending: boolean
  error: unknown
  retrying: boolean
  onRetry: () => void
  onToggle: (id: string, next: boolean) => void
}) {
  if (isPending) return <LoadingState label="Loading capture points" className="min-h-24" />

  if (error) {
    return (
      <ErrorState error={error} onRetry={onRetry} retrying={retrying} className="min-h-0 py-4" />
    )
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="No capture points to search"
        description="This account cannot read any capture point. Ask for access, or sign in as someone who can."
      />
    )
  }

  return (
    <ul className="border-border divide-border overflow-hidden rounded-lg border">
      {items.map((sensor) => {
        const checked = chosen.includes(sensor.id)
        return (
          <SensorOption
            key={sensor.id}
            sensor={sensor}
            checked={checked}
            disabled={!checked && atLimit}
            onToggle={(next) => onToggle(sensor.id, next)}
          />
        )
      })}
    </ul>
  )
}
