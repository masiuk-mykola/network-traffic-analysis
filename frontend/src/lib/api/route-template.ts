import { ROUTE_TEMPLATES } from './generated/routes.gen'

/**
 * The API keys its limits by route template: a delay named on `/v1/searches/srch_a` also covers
 * `/v1/searches/srch_b`. An address the document does not describe is its own template, so a delay
 * is never applied more widely than it was given.
 */
const SEGMENTS: ReadonlyArray<readonly [string, readonly string[]]> = ROUTE_TEMPLATES.map(
  (template) => [template, template.split('/')] as const,
)

export function routeTemplate(path: string): string {
  const bare = path.split(/[?#]/)[0] ?? path
  const parts = bare.split('/')

  let best: string | null = null
  let bestLiterals = -1

  for (const [template, segments] of SEGMENTS) {
    if (segments.length !== parts.length) continue

    const literals = countLiteralMatches(segments, parts)
    // With equal lengths, the template with more literal segments is the more specific one.
    if (literals > bestLiterals) {
      best = template
      bestLiterals = literals
    }
  }

  return best ?? bare
}

/** How many segments matched literally, or -1 when the template does not match at all. */
function countLiteralMatches(segments: readonly string[], parts: readonly string[]): number {
  let literals = 0
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index] ?? ''
    if (segment.startsWith('{') && segment.endsWith('}')) continue
    if (segment !== parts[index]) return -1
    literals += 1
  }
  return literals
}
