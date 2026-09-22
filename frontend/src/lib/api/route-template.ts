import { ROUTE_TEMPLATES } from './generated/routes.gen'

/**
 * Which template an address belongs to.
 *
 * The API's limits are keyed by route template, not by the address that hit them: a delay named on
 * `/v1/searches/srch_a` covers `/v1/searches/srch_b` and the `DELETE` of either. The client cannot
 * honour a window it cannot name, so every address it is about to send is resolved here first.
 *
 * An address the document does not describe becomes its own window — narrower than the truth,
 * never wider, so an unknown endpoint can only ever be waited for too little rather than a delay
 * being applied to requests it was never given for.
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
    // A literal segment beats a placeholder, so `/v1/enrich/ips` wins over `/v1/enrich/ips/{ip}`
    // would if they were ever the same length.
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
