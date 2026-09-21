/** A published path is dotted, and `[]` means "each element of this list". */
const LIST = '[]'

/** A value found in a decoded transaction, named by where it actually sits. */
export type DecodedEntry = { path: string; value: unknown }

/**
 * Every value a published path names inside a decoded transaction, with the concrete path each one
 * came from.
 *
 * The description is written for the canonical decoder; an older one puts a scalar where an object
 * belongs, or a single object where a list belongs. Nothing here corrects that — a path that does
 * not fit the payload simply names nothing, and the value surfaces as undescribed instead.
 */
export function entriesAt(decoded: unknown, path: string): DecodedEntry[] {
  let found: DecodedEntry[] = [{ path: '', value: decoded }]

  for (const segment of path.split('.')) {
    const wantsList = segment.endsWith(LIST)
    const key = wantsList ? segment.slice(0, -LIST.length) : segment

    found = found.flatMap((entry) => step(entry, key))
    if (wantsList) found = found.flatMap(expand)
  }

  return found.filter((entry) => entry.value !== null && entry.value !== undefined)
}

export function valuesAt(decoded: unknown, path: string): unknown[] {
  return entriesAt(decoded, path).map((entry) => entry.value)
}

/** Every value in the payload, named by its path. An empty list or object holds nothing to show. */
export function leaves(decoded: unknown, prefix = ''): DecodedEntry[] {
  if (Array.isArray(decoded)) {
    return decoded.flatMap((item, index) => leaves(item, `${prefix}[${index}]`))
  }

  if (typeof decoded === 'object' && decoded !== null) {
    return Object.entries(decoded).flatMap(([key, value]) =>
      leaves(value, prefix ? `${prefix}.${key}` : key),
    )
  }

  if (decoded === null || decoded === undefined) return []
  return [{ path: prefix, value: decoded }]
}

function step(entry: DecodedEntry, key: string): DecodedEntry[] {
  if (!key) return [entry]

  const { path, value } = entry
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return []

  const found = (value as Record<string, unknown>)[key]
  return found === undefined ? [] : [{ path: path ? `${path}.${key}` : key, value: found }]
}

function expand(entry: DecodedEntry): DecodedEntry[] {
  if (!Array.isArray(entry.value)) return []
  return entry.value.map((value, index) => ({ path: `${entry.path}[${index}]`, value }))
}
