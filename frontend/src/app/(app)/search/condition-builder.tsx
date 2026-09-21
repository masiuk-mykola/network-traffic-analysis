'use client'

import { Plus } from 'lucide-react'

import {
  describeCondition,
  emptyRow,
  type ConditionRow as Row,
  type FieldCatalogue,
  type Join,
} from '@lib/search/condition'
import { EmptyState, ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

import { ConditionRow } from './condition-row'

type ConditionBuilderProps = {
  fields: FieldCatalogue
  isPending: boolean
  error: unknown
  onRetry: () => void
  rows: Row[]
  join: Join
  onChange: (rows: Row[], join: Join) => void
}

export function ConditionBuilder({
  fields,
  isPending,
  error,
  onRetry,
  rows,
  join,
  onChange,
}: ConditionBuilderProps) {
  if (isPending) return <LoadingState label="Loading fields" />
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (Object.keys(fields).length === 0) {
    return (
      <EmptyState
        title="No fields to search on"
        description="This server published no searchable fields for this account."
      />
    )
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium">Conditions</h2>
        {rows.length > 1 ? (
          <div className="flex items-center gap-1">
            <span className="text-muted text-xs">Match</span>
            {(['all', 'any'] as const).map((option) => (
              <Button
                key={option}
                size="sm"
                variant={join === option ? 'primary' : 'ghost'}
                aria-pressed={join === option}
                onClick={() => onChange(rows, option)}
              >
                {option}
              </Button>
            ))}
          </div>
        ) : null}
      </div>

      {rows.length === 0 ? (
        <p className="text-muted text-sm">
          No conditions: the search would return every session in the window.
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <ConditionRow
              key={row.id}
              row={row}
              fields={fields}
              problem={describeCondition(row, fields[row.field])}
              onChange={(next) =>
                onChange(
                  rows.map((current) => (current.id === next.id ? next : current)),
                  join,
                )
              }
              onRemove={() =>
                onChange(
                  rows.filter((current) => current.id !== row.id),
                  join,
                )
              }
            />
          ))}
        </ul>
      )}

      <Button variant="secondary" size="sm" onClick={() => onChange([...rows, emptyRow()], join)}>
        <Plus aria-hidden className="size-4" />
        Add condition
      </Button>
    </section>
  )
}
