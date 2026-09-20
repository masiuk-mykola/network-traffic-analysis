import 'server-only'

import { cookies } from 'next/headers'
import { randomUUID } from 'node:crypto'

/** An opaque id — the only part of a session the browser gets to hold. */
export const SESSION_COOKIE = 'capture_sid'

export async function currentSessionId(): Promise<string | undefined> {
  const jar = await cookies()
  return jar.get(SESSION_COOKIE)?.value
}

export function newSessionId(): string {
  return randomUUID()
}

export async function setSessionCookie(id: string): Promise<void> {
  const jar = await cookies()
  jar.set(SESSION_COOKIE, id, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
  })
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies()
  jar.delete(SESSION_COOKIE)
}
