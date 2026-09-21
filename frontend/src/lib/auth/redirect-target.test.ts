import { describe, expect, it } from 'vitest'

import { safeRedirectTarget } from './redirect-target'

describe('safeRedirectTarget', () => {
  it('keeps a plain path inside this app', () => {
    expect(safeRedirectTarget('/sessions/72075232438042624')).toBe('/sessions/72075232438042624')
    expect(safeRedirectTarget('/search?from=2025-10-27')).toBe('/search?from=2025-10-27')
  })

  it('falls back when there is nothing to go back to', () => {
    expect(safeRedirectTarget(null)).toBe('/search')
    expect(safeRedirectTarget(undefined)).toBe('/search')
    expect(safeRedirectTarget('')).toBe('/search')
  })

  it('refuses to send anyone to another site', () => {
    expect(safeRedirectTarget('https://evil.example')).toBe('/search')
    expect(safeRedirectTarget('//evil.example')).toBe('/search')
    expect(safeRedirectTarget('/\\evil.example')).toBe('/search')
    expect(safeRedirectTarget('javascript:alert(1)')).toBe('/search')
  })

  it('sees through an encoded attempt', () => {
    expect(safeRedirectTarget('/%2F%2Fevil.example')).toBe('/search')
    expect(safeRedirectTarget('%2F%2Fevil.example')).toBe('/search')
    expect(safeRedirectTarget('/%5Cevil.example')).toBe('/search')
  })

  it('refuses anything that is not a path at all', () => {
    expect(safeRedirectTarget('search')).toBe('/search')
    expect(safeRedirectTarget('../etc/passwd')).toBe('/search')
  })

  it('does not send anyone back to the sign-in screen', () => {
    expect(safeRedirectTarget('/login')).toBe('/search')
    expect(safeRedirectTarget('/login?next=/search')).toBe('/search')
  })
})
