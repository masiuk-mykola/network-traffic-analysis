import { describe, expect, it } from 'vitest'

import { ROUTE_TEMPLATES } from './generated/routes.gen'
import { routeTemplate } from './route-template'

describe('routeTemplate', () => {
  it('names the template an address belongs to', () => {
    expect(routeTemplate('/v1/searches/srch_52d38d91c6ee')).toBe('/v1/searches/{search_id}')
    expect(routeTemplate('/v1/sessions/18446744073709551615')).toBe('/v1/sessions/{session_id}')
  })

  it('leaves a path with no placeholders as it is', () => {
    expect(routeTemplate('/v1/me')).toBe('/v1/me')
    expect(routeTemplate('/v1/searches')).toBe('/v1/searches')
  })

  it('keeps a nested path apart from its parent', () => {
    // A cursor read and a status read are two windows. Collapsing them would make the client wait
    // for delays it was never given, and — worse — believe it had waited for one it was.
    expect(routeTemplate('/v1/searches/srch_a/results')).toBe('/v1/searches/{search_id}/results')
    expect(routeTemplate('/v1/searches/srch_a/graph')).toBe('/v1/searches/{search_id}/graph')
  })

  it('prefers a literal segment over a placeholder', () => {
    expect(routeTemplate('/v1/enrich/ips')).toBe('/v1/enrich/ips')
    expect(routeTemplate('/v1/enrich/ips/198.51.100.7')).toBe('/v1/enrich/ips/{ip}')
  })

  it('matches every template in the document back to itself', () => {
    for (const template of ROUTE_TEMPLATES) {
      const concrete = template.replace(/\{[^}]+\}/g, 'x')
      expect(routeTemplate(concrete)).toBe(template)
    }
  })

  it('gives every template in the document a window of its own', () => {
    const matched = ROUTE_TEMPLATES.map((template) =>
      routeTemplate(template.replace(/\{[^}]+\}/g, 'x')),
    )
    expect(new Set(matched).size).toBe(ROUTE_TEMPLATES.length)
  })

  it('makes an address the document does not describe its own window', () => {
    expect(routeTemplate('/v1/not/a/known/path')).toBe('/v1/not/a/known/path')
    expect(routeTemplate('/v1/searches/a/b/c/d')).toBe('/v1/searches/a/b/c/d')
  })

  it('ignores anything after the path itself', () => {
    expect(routeTemplate('/v1/searches/srch_a/results?limit=500')).toBe(
      '/v1/searches/{search_id}/results',
    )
  })
})
