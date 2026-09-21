import { describe, expect, it } from 'vitest'

import { credentialsSchema } from './credentials'

function check(input: unknown) {
  return credentialsSchema.safeParse(input)
}

describe('credentialsSchema', () => {
  it('accepts a plausible pair', () => {
    const result = check({ email: 'ana@quillmere.example', password: 'demo-analyst' })

    expect(result.success).toBe(true)
  })

  it('requires both fields, and says which one is missing', () => {
    const result = check({ email: '', password: '' })

    expect(result.success).toBe(false)
    const fields = result.error?.issues.map((issue) => issue.path[0])
    expect(fields).toContain('email')
    expect(fields).toContain('password')
  })

  it('refuses something that cannot be an email, so the attempt is not spent', () => {
    expect(check({ email: 'not-an-email', password: 'demo-analyst' }).success).toBe(false)
  })

  it('keeps within the limits the API declares', () => {
    const longEmail = `${'a'.repeat(250)}@b.co`
    expect(check({ email: longEmail, password: 'x' }).success).toBe(false)
    expect(check({ email: 'a@b.co', password: 'x'.repeat(257) }).success).toBe(false)
    expect(check({ email: 'a@b.co', password: 'x'.repeat(256) }).success).toBe(true)
  })

  it('trims an email that was pasted with whitespace', () => {
    const result = check({ email: '  ana@quillmere.example  ', password: 'demo-analyst' })

    expect(result.success).toBe(true)
    expect(result.data?.email).toBe('ana@quillmere.example')
  })
})
