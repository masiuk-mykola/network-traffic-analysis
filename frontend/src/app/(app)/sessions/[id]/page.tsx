import { ApiError } from '@api/client'
import { zGetSessionResponse } from '@api/generated/zod.gen'
import { callApi } from '@api/server'
import { NOT_FOUND, type Session, type SessionStatus } from '@lib/session/session-state'

import { SessionView } from './session-view'

export default async function SessionPage({ params }: PageProps<'/sessions/[id]'>) {
  const { id } = await params

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-6">
      <SessionView sessionId={id} initialStatus={await readSession(id)} />
    </main>
  )
}

/**
 * Read here so a pasted address answers in one request, and so a session the server does not have
 * is denied once rather than by every copy of the screen React mounts.
 */
async function readSession(sessionId: string): Promise<SessionStatus | undefined> {
  try {
    const { data } = await callApi({
      path: `/v1/sessions/${encodeURIComponent(sessionId)}`,
      schema: zGetSessionResponse,
    })
    return data as Session
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return NOT_FOUND
    // Anything else is the screen's to report, with its retry.
    return undefined
  }
}
