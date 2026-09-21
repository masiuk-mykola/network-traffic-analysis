import type { components } from '@api/schema'

import { entriesAt, leaves, type DecodedEntry } from './decoded-path'

type SchemaField = components['schemas']['SchemaField']

export type DescribedField = {
  path: string
  title: string
  type: string
  unit?: string
  sensitive: boolean
  values: unknown[]
}

export type SplitDecoded = {
  /** In the order the server publishes, and only the ones this session carries. */
  described: DescribedField[]
  /** Everything the description never claimed, under the path it actually sits at. */
  undescribed: DecodedEntry[]
}

/**
 * What to show of a decoded transaction, and under which name.
 *
 * A described field with no value here is left out rather than shown empty, and a value the
 * description never named is still shown — a session from an older decoder would otherwise arrive
 * as a nearly blank screen.
 */
export function splitDecoded(decoded: unknown, fields: readonly SchemaField[]): SplitDecoded {
  const claimed = new Set<string>()
  const described: DescribedField[] = []

  for (const field of fields) {
    const found = entriesAt(decoded, field.path)
    if (found.length === 0) continue

    for (const entry of found) claimed.add(entry.path)
    described.push({
      path: field.path,
      title: field.title,
      type: field.type,
      ...(field.unit === undefined ? {} : { unit: field.unit }),
      sensitive: field.sensitive ?? false,
      values: found.map((entry) => entry.value),
    })
  }

  return {
    described,
    undescribed: leaves(decoded).filter((entry) => !claimed.has(entry.path)),
  }
}
