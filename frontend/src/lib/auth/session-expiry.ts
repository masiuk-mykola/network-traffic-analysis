import { isHttpError } from '@api/http-error'

const SESSION_GONE = 'session_revoked'

type Options = {
  /** Cancel what is in flight, drop the cache, explain, and leave. Called at most once per session. */
  onExpired: () => void
  /** True while the app is already at sign in, where a stray failure must not bounce anyone. */
  isSignedOut?: () => boolean
}

export type ExpiryHandler = {
  handleFailure: (error: unknown) => void
  /** Arms the reaction again, once a new session exists. */
  rearm: () => void
}

let active: ExpiryHandler | null = null

/** The provider registers the live handler here, so plain readers can report too. */
export function setExpiryHandler(handler: ExpiryHandler | null): void {
  active = handler
}

/** Called from the one browser reader; a no-op on the server and before the app mounts. */
export function reportFailure(error: unknown): void {
  active?.handleFailure(error)
}

/**
 * The single reaction to a session that is gone. Several requests fail in the same tick when a
 * session dies mid-screen; without the flag each one would cancel, clear and navigate on its own.
 */
export function createExpiryHandler({ onExpired, isSignedOut }: Options): ExpiryHandler {
  let handled = false

  return {
    handleFailure(error: unknown) {
      if (handled) return
      if (!isHttpError(error) || error.code !== SESSION_GONE) return
      if (isSignedOut?.()) return

      handled = true
      onExpired()
    },
    rearm() {
      handled = false
    },
  }
}
