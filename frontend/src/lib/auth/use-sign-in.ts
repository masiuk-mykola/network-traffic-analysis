'use client'

import { useMutation } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'

import { HttpError } from '@api/http-error'

import { DEFAULT_TARGET } from './redirect-target'
import type { Credentials } from './credentials'

/**
 * Posts the credentials to our own route handler — the API token is exchanged and kept server-side,
 * and the browser only receives the profile. Never retried: a refused password must not be sent twice.
 */
export function useSignIn(destination: string = DEFAULT_TARGET) {
  const router = useRouter()

  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json' },
        body: JSON.stringify(credentials),
      })

      if (!res.ok) throw await HttpError.fromResponse(res)
      return (await res.json()) as { user: { display_name: string } }
    },
    retry: false,
    onSuccess: () => {
      // replace, so the back button does not return to a form that is no longer needed.
      router.replace(destination)
      router.refresh()
    },
  })
}
