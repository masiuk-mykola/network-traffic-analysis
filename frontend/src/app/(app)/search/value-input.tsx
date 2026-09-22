'use client'

import type { FieldDef } from '@lib/search/condition'
import { valueArity } from '@lib/search/condition'
import { useEnum } from '@lib/search/use-enum'
import { Button, Input } from '@/components/ui'
import { Select } from '@/components/form/select'

type ValueInputProps = {
  field: FieldDef | undefined
  op: string
  values: string[]
  onChange: (values: string[]) => void
}

const NUMERIC = new Set(['port', 'number', 'bytes', 'duration_ms'])

/** The shape of the value entry is decided by the field and the comparison, never guessed. */
export function ValueInput({ field, op, values, onChange }: ValueInputProps) {
  const arity = valueArity(op)
  const closed = useEnum(field?.enum_name)

  if (!field || !op || arity === 'none') return null

  if (field.enum_name || field.enum) {
    // A list that cannot be read must not block the condition: the value is typed instead, and the
    // list can be asked for again.
    if (!field.enum && closed.isError) {
      return (
        <div className="flex-1 space-y-1">
          <Input
            aria-label="Value"
            value={values[0] ?? ''}
            placeholder={field.example}
            onChange={(event) => onChange([event.target.value])}
          />
          <p className="text-muted flex items-center gap-2 text-xs">
            The list of values could not be read. Type it, or
            <Button
              variant="ghost"
              size="sm"
              disabled={closed.isFetching}
              onClick={() => void closed.refetch()}
            >
              {closed.isFetching ? 'Trying again' : 'Try again'}
            </Button>
          </p>
        </div>
      )
    }

    const options = field.enum
      ? field.enum.map((value) => ({ value, label: value }))
      : (closed.data?.values.map((entry) => ({ value: entry.value, label: entry.label })) ?? [])

    return (
      <Select
        aria-label="Value"
        value={values[0] ?? ''}
        onValueChange={(value) => onChange([value])}
        options={options}
        placeholder={closed.isPending && !field.enum ? 'Loading…' : 'Choose a value'}
        disabled={closed.isPending && !field.enum}
        className="min-w-44 flex-1"
      />
    )
  }

  if (arity === 'two') {
    return (
      <div className="flex flex-1 items-center gap-2">
        <Input
          aria-label="From"
          inputMode={NUMERIC.has(field.type) ? 'numeric' : 'text'}
          value={values[0] ?? ''}
          placeholder={field.example}
          onChange={(event) => onChange([event.target.value, values[1] ?? ''])}
        />
        <span className="text-muted text-xs">to</span>
        <Input
          aria-label="To"
          inputMode={NUMERIC.has(field.type) ? 'numeric' : 'text'}
          value={values[1] ?? ''}
          onChange={(event) => onChange([values[0] ?? '', event.target.value])}
        />
      </div>
    )
  }

  if (arity === 'set') {
    return (
      <Input
        aria-label="Values"
        className="flex-1"
        value={values.join(', ')}
        placeholder="One or more, separated by commas"
        onChange={(event) =>
          onChange(
            event.target.value
              .split(',')
              .map((value) => value.trim())
              .filter(Boolean),
          )
        }
      />
    )
  }

  return (
    <Input
      aria-label="Value"
      className="flex-1"
      inputMode={NUMERIC.has(field.type) ? 'numeric' : 'text'}
      placeholder={field.example}
      value={values[0] ?? ''}
      onChange={(event) => onChange([event.target.value])}
    />
  )
}
