'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState } from 'react'

import { formatTimestamp } from '@lib/format'
import { ROUTES } from '@lib/routes'
import { type ConditionRow, type FieldCatalogue, type Join } from '@lib/search/condition'
import {
  describeQuery,
  MAX_SENSORS,
  toQueryString,
  type QueryState,
} from '@lib/search/query-params'
import { describeEstimateGap, toEstimateParams } from '@lib/search/estimate-params'
import { useFields } from '@lib/search/use-fields'
import { useSearch } from '@lib/search/use-search'
import type { SearchStatus } from '@lib/search/search-state'
import { useSensors } from '@lib/search/use-sensors'
import { useDebounced } from '@lib/use-debounced'
import { defaultWindow } from '@lib/search/window'
import { Field } from '@/components/form/field'
import { Input } from '@/components/ui'

import { ConditionBuilder } from './condition-builder'
import { EstimateLine } from './estimate-line'
import { ResultsTable } from './results-table'
import { RunControl } from './run-control'
import { SensorList } from './sensor-list'

const ESTIMATE_DELAY_MS = 400

/** The form keeps the choices locally and mirrors them into the address bar as they change. */
export function QueryForm({
  initial,
  fields: initialFields,
  readable,
  initialStatus,
}: {
  initial: QueryState
  fields?: FieldCatalogue
  /**
   * The points this account may read, from its profile. The list the server publishes holds every
   * point there is, readable or not, so this is the only thing that says which are open to us.
   */
  readable: readonly string[]
  /** What the page read about the job the address named, so the browser does not ask again. */
  initialStatus?: SearchStatus
}) {
  const router = useRouter()
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
  const estimateGap = describeEstimateGap(settled)
  const running = useSearch(query.searchId, { searchId: initial.searchId, status: initialStatus })

  const landmark = `${query.searchId ?? ''}|${query.sort}`
  const previousLandmark = useRef(landmark)

  useEffect(() => {
    // The query is client state; the address bar only has to reflect it for a reload or a shared
    // link. A form left mounted by a navigation away from this screen must not rewrite the address
    // of the screen that replaced it.
    if (window.location.pathname !== ROUTES.search) return

    const search = toQueryString(query)
    const next = search ? `${ROUTES.search}?${search}` : ROUTES.search
    if (`${window.location.pathname}${window.location.search}` !== next) {
      // Starting a search or changing its order is a place worth coming back to, and only the
      // router can create an entry it will restore with these parameters — an entry written
      // straight to the history is restored as a bare `/search`. Everything in between is an edit
      // of the address we are already on, which must not re-render the page on the server.
      const landmarkMoved = previousLandmark.current !== landmark
      previousLandmark.current = landmark
      if (landmarkMoved) router.push(next, { scroll: false })
      else window.history.replaceState(null, '', next)
    }
  }, [query, landmark, router])

  const problem = describeQuery(query, fields.data ?? {})

  return (
    <form
      className="space-y-6"
      onSubmit={(event) => {
        event.preventDefault()
        // Running the search is the next step; this form only decides what would be searched.
      }}
    >
      <SensorList
        items={items}
        chosen={query.sensorIds}
        readable={readable}
        isPending={sensors.isPending}
        error={sensors.isError ? sensors.error : null}
        retrying={sensors.isFetching}
        onRetry={() => void sensors.refetch()}
        onToggle={(id, next) => {
          setState((current) => ({
            ...current,
            sensorIds: next
              ? [...current.sensorIds, id].slice(0, MAX_SENSORS)
              : current.sensorIds.filter((chosen) => chosen !== id),
          }))
        }}
      />

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
        <EstimateLine params={estimateParams} gap={estimateGap} />
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

      <ResultsTable
        searchId={query.searchId}
        status={running.data}
        sort={query.sort}
        onSortChange={(sort) => setState({ ...query, sort })}
      />
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
