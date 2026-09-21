'use client'

import { X } from 'lucide-react'

import type { ConditionRow as Row, FieldCatalogue } from '@lib/search/condition'
import { valueArity } from '@lib/search/condition'
import { Select } from '@/components/form/select'
import { Button } from '@/components/ui'

import { ValueInput } from './value-input'

type ConditionRowProps = {
  row: Row
  fields: FieldCatalogue
  problem: string | null
  onChange: (row: Row) => void
  onRemove: () => void
}

const OPERATOR_LABELS: Record<string, string> = {
  eq: 'is',
  in: 'is one of',
  cidr: 'is inside',
  glob: 'matches',
  gte: 'at least',
  lte: 'at most',
  between: 'between',
  exists: 'is present',
}

export function ConditionRow({ row, fields, problem, onChange, onRemove }: ConditionRowProps) {
  const field = fields[row.field]

  const fieldOptions = Object.values(fields).map((entry) => ({
    value: entry.name,
    label: entry.label,
    // The catalogue names protocol fields `dns.*`, `http.*` and so on; that prefix is the group.
    group: entry.name.includes('.') ? entry.name.split('.')[0] : 'session',
  }))

  const operatorOptions = (field?.operators ?? []).map((op) => ({
    value: op,
    label: OPERATOR_LABELS[op] ?? op,
  }))

  return (
    <li className="border-border space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant={row.negated ? 'primary' : 'ghost'}
          size="sm"
          aria-pressed={row.negated}
          onClick={() => onChange({ ...row, negated: !row.negated })}
        >
          not
        </Button>

        <Select
          aria-label="Field"
          value={row.field}
          onValueChange={(name) => {
            const next = fields[name]
            // Carrying an operator the new field does not allow would produce a refused search.
            const op = next?.operators.includes(row.op as never) ? row.op : ''
            onChange({ ...row, field: name, op, values: op === row.op ? row.values : [] })
          }}
          options={fieldOptions}
          placeholder="Choose a field"
          className="min-w-48"
        />

        <Select
          aria-label="Comparison"
          value={row.op}
          onValueChange={(op) =>
            onChange({
              ...row,
              op,
              values: valueArity(op) === valueArity(row.op) ? row.values : [],
            })
          }
          options={operatorOptions}
          placeholder="Comparison"
          disabled={!field}
          className="min-w-36"
        />

        <ValueInput
          field={field}
          op={row.op}
          values={row.values}
          onChange={(values) => onChange({ ...row, values })}
        />

        <Button variant="ghost" size="sm" aria-label="Remove condition" onClick={onRemove}>
          <X aria-hidden className="size-4" />
        </Button>
      </div>

      {problem ? <p className="text-danger text-xs">{problem}</p> : null}
    </li>
  )
}
