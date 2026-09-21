import { describeCondition, emptyRow, type ConditionRow, type FieldCatalogue } from './condition'

const NEGATED = '!'

/**
 * The API's own filter shorthand, `field:op:v1,v2`, which `/v1/estimate` already accepts — so the
 * address bar stays readable and the estimate can reuse it. A leading `!` negates the row.
 *
 * Values are encoded individually: a glob or a user agent can contain both separators.
 */
export function conditionsToParams(rows: readonly ConditionRow[]): string[] {
  return rows
    .filter((row) => describeCondition(row) === null)
    .map((row) => {
      const values = row.values.map((value) => encodeURIComponent(value)).join(',')
      const head = `${row.negated ? NEGATED : ''}${row.field}:${row.op}`
      return values ? `${head}:${values}` : head
    })
}

/** Anything unusable is dropped: this arrives from a link someone else wrote. */
export function parseConditions(params: URLSearchParams, fields: FieldCatalogue): ConditionRow[] {
  return params
    .getAll('f')
    .map((raw) => parseOne(raw, fields))
    .filter((row): row is ConditionRow => row !== null)
}

function parseOne(raw: string, fields: FieldCatalogue): ConditionRow | null {
  const negated = raw.startsWith(NEGATED)
  const [name, op, rest] = (negated ? raw.slice(1) : raw).split(':', 3)
  if (!name || !op) return null

  const field = fields[name]
  if (!field || !field.operators.includes(op as never)) return null

  const values = rest ? rest.split(',').map((value) => decodeURIComponent(value)) : []
  const row: ConditionRow = { ...emptyRow(), field: name, op, values, negated }

  return describeCondition(row, field) === null ? row : null
}
