'use client'

import { useEffect, useMemo, useState } from 'react'

import { formatTimestamp } from '@lib/format'
import { type ConditionRow, type FieldCatalogue, type Join } from '@lib/search/condition'
import {
  describeQuery,
  MAX_SENSORS,
  toQueryString,
  type QueryState,
} from '@lib/search/query-params'
import { toEstimateParams } from '@lib/search/estimate-params'
import { useFields } from '@lib/search/use-fields'
import { useSearch } from '@lib/search/use-search'
import { useSensors } from '@lib/search/use-sensors'
import { useDebounced } from '@lib/use-debounced'
import { defaultWindow } from '@lib/search/window'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Field } from '@/components/form/field'
import { Input } from '@/components/ui'

import { ConditionBuilder } from './condition-builder'
import { EstimateLine } from './estimate-line'
import { RunControl } from './run-control'
import { SensorOption } from './sensor-option'

const ESTIMATE_DELAY_MS = 400

/** The form keeps the choices locally and mirrors them into the address bar as they change. */
export function QueryForm({
  initial,
  fields: initialFields,
}: {
  initial: QueryState
  fields?: FieldCatalogue
}) {
  const sensors = useSensors()
  const fields = useFields(initialFields)
  const [state, setState] = useState<QueryState>(initial)

  const items = useMemo(() => sensors.data?.items ?? [], [sensors.data])

  // The window is derived rather than seeded: the traffic ends in the past, so until someone picks
  // one, the right default is the last moment these points reported.
  const query = useMemo((): QueryState => {
    if (state.from && state.to) return state
    const chosen = items.filter((sensor) => state.sensorIds.includes(sensor.id))
    const suggested = defaultWindow(chosen.length > 0 ? chosen : items)
    return suggested ? { ...state, ...suggested } : state
  }, [state, items])

  // The endpoint allows only a few requests per second, so it is asked about a settled query.
  // Both hooks run before any early return, or their order would change between renders.
  const settled = useDebounced(query, ESTIMATE_DELAY_MS)
  const estimateParams = toEstimateParams(settled, fields.data ?? {})
  const running = useSearch(query.searchId)

  useEffect(() => {
    // The query is client state; the address bar only has to reflect it for a reload or a shared
    // link. Going through the router would re-render the page on the server for every keystroke —
    // and each of those renders reads the field catalogue again.
    const search = toQueryString(query)
    const next = search ? `/search?${search}` : '/search'
    if (`${window.location.pathname}${window.location.search}` !== next) {
      window.history.replaceState(null, '', next)
    }
  }, [query])

  if (sensors.isPending) return <LoadingState label="Loading capture points" />
  if (sensors.isError) {
    return <ErrorState error={sensors.error} onRetry={() => void sensors.refetch()} />
  }
  if (items.length === 0) {
    return (
      <EmptyState
        title="No capture points to search"
        description="This account cannot read any capture point. Ask for access, or sign in as someone who can."
      />
    )
  }

  const atLimit = query.sensorIds.length >= MAX_SENSORS
  const problem = describeQuery(query, fields.data ?? {})

  return (
    <form
      className="space-y-6"
      onSubmit={(event) => {
        event.preventDefault()
        // Running the search is the next step; this form only decides what would be searched.
      }}
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Capture points</legend>
        <p className="text-muted text-xs">
          Between one and {MAX_SENSORS}. A point that is behind has not reported its most recent
          traffic yet.
        </p>
        <ul className="border-border divide-border overflow-hidden rounded-lg border">
          {items.map((sensor) => {
            const checked = query.sensorIds.includes(sensor.id)
            return (
              <SensorOption
                key={sensor.id}
                sensor={sensor}
                checked={checked}
                disabled={!checked && atLimit}
                onToggle={(next) => {
                  setState((current) => ({
                    ...current,
                    sensorIds: next
                      ? [...current.sensorIds, sensor.id].slice(0, MAX_SENSORS)
                      : current.sensorIds.filter((id) => id !== sensor.id),
                  }))
                }}
              />
            )
          })}
        </ul>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="From (UTC)">
          {(props) => (
            <Input
              {...props}
              type="datetime-local"
              step="1"
              value={toLocalInput(query.from)}
              onChange={(event) => setState({ ...query, from: fromLocalInput(event.target.value) })}
            />
          )}
        </Field>
        <Field label="To (UTC)">
          {(props) => (
            <Input
              {...props}
              type="datetime-local"
              step="1"
              value={toLocalInput(query.to)}
              onChange={(event) => setState({ ...query, to: fromLocalInput(event.target.value) })}
            />
          )}
        </Field>
      </div>

      {query.to ? (
        <p className="text-muted text-xs">
          This capture ends at {formatTimestamp(query.to)}, so the window is not today.
        </p>
      ) : null}

      <ConditionBuilder
        fields={fields.data ?? {}}
        isPending={fields.isPending}
        error={fields.isError ? fields.error : null}
        onRetry={() => void fields.refetch()}
        rows={query.conditions}
        join={query.join}
        onChange={(conditions: ConditionRow[], join: Join) =>
          setState({ ...query, conditions, join })
        }
      />

      {problem ? (
        <p role="alert" className="text-danger text-sm">
          {problem}
        </p>
      ) : null}

      <div className="space-y-3">
        <EstimateLine params={estimateParams} />
        <RunControl
          query={query}
          fields={fields.data ?? {}}
          problem={problem}
          watching={{
            searchId: query.searchId,
            status: running.data,
            error: running.error,
            isPending: running.isPending,
          }}
          onStarted={(search) => setState({ ...query, searchId: search.id })}
        />
      </div>
    </form>
  )
}

/** `datetime-local` speaks the browser's zone; everything here is UTC, so convert explicitly. */
function toLocalInput(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toISOString().slice(0, 19)
}

function fromLocalInput(value: string): string | null {
  if (!value) return null
  const parsed = Date.parse(`${value}Z`)
  return Number.isNaN(parsed) ? null : new Date(parsed).toISOString()
}
