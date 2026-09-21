import type { components } from '@api/schema'

export type Session = components['schemas']['Session']

/**
 * An address can name a session that never existed, or one this account may not read; the server
 * answers both the same way. It is a thing to state, not a failure to retry.
 */
export const NOT_FOUND = { notFound: true } as const

export type SessionStatus = Session | typeof NOT_FOUND

export function isNotFound(status: SessionStatus): status is typeof NOT_FOUND {
  return 'notFound' in status
}
