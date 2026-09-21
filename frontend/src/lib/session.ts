import 'server-only'

import { cookies } from 'next/headers'
import { randomUUID } from 'node:crypto'

/** An opaque id — the only part of a session the browser gets to hold. */
export const SESSION_COOKIE = 'capture_sid'

export async function currentSessionId(): Promise<string | undefined> {
  const cookieStore = await cookies()
  return cookieStore.get(SESSION_COOKIE)?.value
}

export function newSessionId(): string {
  return randomUUID()
}

export async function setSessionCookie(id: string): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.set(SESSION_COOKIE, id, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
  })
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies()
  cookieStore.delete(SESSION_COOKIE)
}
