import 'server-only'

import { ApiError, rawFetch, type TokenPair } from './client'
import { zRefreshResponse } from './generated/zod.gen'

/**
 * Tokens live here, on the server; the browser only ever sees a session id.
 * In-memory is enough for a single instance — swap the Map for Redis to scale out.
 */
type Entry = {
  access: string
  accessExpiresAt: number
  refresh: string
  inflight: Promise<Entry> | null
  revoked: boolean
}

const REFRESH_SKEW_MS = 5_000

const sessions = new Map<string, Entry>()

export function putSession(id: string, pair: TokenPair): void {
  sessions.set(id, {
    access: pair.access_token,
    accessExpiresAt: Date.now() + pair.access_expires_in * 1000 - REFRESH_SKEW_MS,
    refresh: pair.refresh_token,
    inflight: null,
    revoked: false,
  })
}

export function dropSession(id: string): void {
  sessions.delete(id)
}

export function hasSession(id: string | undefined): boolean {
  return Boolean(id && sessions.has(id))
}

export async function accessTokenFor(id: string): Promise<string> {
  const entry = sessions.get(id)
  if (!entry || entry.revoked) throw new SessionGone()
  if (Date.now() < entry.accessExpiresAt) return entry.access
  const fresh = await refreshOnce(id, entry)
  return fresh.access
}

export async function refreshAfterUnauthorized(id: string): Promise<string> {
  const entry = sessions.get(id)
  if (!entry || entry.revoked) throw new SessionGone()
  const fresh = await refreshOnce(id, entry)
  return fresh.access
}

/**
 * Refresh tokens are single-use with no grace period: presenting a burnt one revokes
 * the whole family. So concurrent callers share one in-flight refresh.
 */
function refreshOnce(id: string, entry: Entry): Promise<Entry> {
  if (entry.inflight) return entry.inflight

  const inflight = (async () => {
    try {
      const { data } = await rawFetch<TokenPair>({
        method: 'POST',
        path: '/v1/auth/refresh',
        body: { refresh_token: entry.refresh },
        schema: zRefreshResponse,
      })
      const next: Entry = {
        access: data.access_token,
        accessExpiresAt: Date.now() + data.access_expires_in * 1000 - REFRESH_SKEW_MS,
        refresh: data.refresh_token,
        inflight: null,
        revoked: false,
      }
      sessions.set(id, next)
      return next
    } catch (error) {
      entry.revoked = true
      sessions.delete(id)
      if (error instanceof ApiError && error.status === 401) throw new SessionGone()
      throw error
    } finally {
      entry.inflight = null
    }
  })()

  entry.inflight = inflight
  return inflight
}

export class SessionGone extends Error {
  constructor() {
    super('session is gone')
    this.name = 'SessionGone'
  }
}
