import type { components } from '@api/schema'

export type FieldDef = components['schemas']['FieldDef']
export type FilterNode = components['schemas']['FilterNode']
export type FieldCatalogue = Record<string, FieldDef>

export type Join = 'all' | 'any'

export type ConditionRow = {
  id: string
  field: string
  op: string
  values: string[]
  negated: boolean
}

/** The API's own arity rules, which decide both what we send and what we ask the person for. */
const MAX_SET_VALUES = 50
const NUMERIC_TYPES = new Set(['port', 'number', 'bytes', 'duration_ms'])

let nextRowId = 0

export function emptyRow(): ConditionRow {
  nextRowId += 1
  return { id: `row-${nextRowId}`, field: '', op: '', values: [], negated: false }
}

export function valueArity(op: string): 'none' | 'one' | 'two' | 'set' {
  if (op === 'exists') return 'none'
  if (op === 'between') return 'two'
  if (op === 'in') return 'set'
  return 'one'
}

/** Builds what `POST /v1/searches` takes. Rows that are not finished are left out by the caller. */
export function toFilterNode(
  rows: readonly ConditionRow[],
  join: Join,
  fields: FieldCatalogue = {},
): FilterNode | null {
  if (rows.length === 0) return null

  const nodes = rows.map((row) => {
    const leaf = toLeaf(row, fields[row.field])
    return row.negated ? { not: leaf } : leaf
  })

  return join === 'any' ? { any: nodes } : { all: nodes }
}

function toLeaf(row: ConditionRow, field: FieldDef | undefined): FilterNode {
  const cast = (value: string) => castValue(value, field)

  switch (valueArity(row.op)) {
    case 'none':
      return { field: row.field, op: row.op } as FilterNode
    case 'two':
    case 'set':
      return { field: row.field, op: row.op, values: row.values.map(cast) } as FilterNode
    default:
      return { field: row.field, op: row.op, value: cast(row.values[0] ?? '') } as FilterNode
  }
}

/** A port is a number to the API even though the form collects text. */
function castValue(value: string, field: FieldDef | undefined): string | number {
  if (!field || !NUMERIC_TYPES.has(field.type)) return value
  const asNumber = Number(value)
  return Number.isFinite(asNumber) && value.trim() !== '' ? asNumber : value
}

/**
 * What is still wrong with a row, in the words the person needs. Null when it is ready to send.
 * Catching this here is the difference between an empty result and a refused search.
 */
export function describeCondition(row: ConditionRow, field?: FieldDef): string | null {
  if (!row.field) return 'Choose a field.'
  if (!row.op) return 'Choose a comparison.'
  if (field && !field.operators.includes(row.op as never)) {
    return `${field.label} does not allow that comparison.`
  }

  const filled = row.values.filter((value) => value.trim() !== '')

  switch (valueArity(row.op)) {
    case 'none':
      return null
    case 'two':
      return filled.length === 2 ? null : 'A range needs two values.'
    case 'set':
      if (filled.length === 0) return 'Add at least one value.'
      return filled.length > MAX_SET_VALUES ? `No more than ${MAX_SET_VALUES} values.` : null
    default:
      return filled.length === 1 ? null : 'Enter a value.'
  }
}
