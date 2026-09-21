'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { isHttpError } from '@api/http-error'
import { sessionKey } from '@api/keys'

import { NOT_FOUND, type Session, type SessionStatus } from './session-state'

/** What the page already read about this session, so the browser does not ask for it again. */
export type InitialSession = { sessionId: string; status: SessionStatus | undefined }

/** One session in full. A decoded session never changes, so it is read once and kept. */
export function useSession(sessionId: string, initial?: InitialSession) {
  const inherited = initial && initial.sessionId === sessionId ? initial.status : undefined

  return useQuery<SessionStatus>({
    queryKey: sessionKey(sessionId),
    queryFn: async ({ signal }) => {
      try {
        return await fetchJson<Session>(`sessions/${encodeURIComponent(sessionId)}`, { signal })
      } catch (error) {
        if (isHttpError(error) && error.status === 404) return NOT_FOUND
        throw error
      }
    },
    initialData: inherited,
    staleTime: Infinity,
  })
}
