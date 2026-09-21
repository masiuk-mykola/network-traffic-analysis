'use client'

import { useMutation } from '@tanstack/react-query'
import { useRef } from 'react'

import { HttpError } from '@api/http-error'
import type { components } from '@api/schema'

import { idempotencyKeyFor, type SearchBody } from './search-body'

type Search = components['schemas']['Search']

/**
 * Starts a search, replacing the one this screen started before it. The order matters: the old job
 * is ended first, so a failure to start does not leave two of the three slots occupied.
 *
 * Never retried automatically — a retry here is the person pressing again, and the label derived
 * from the query is what makes that return the same job instead of a twin.
 */
export function useRunSearch(onStarted: (search: Search) => void) {
  // Only a job this screen started may be deleted; the id in the address bar can be edited by hand.
  const started = useRef<Search | null>(null)
  const startedLabel = useRef<string | null>(null)

  const mutation = useMutation({
    mutationFn: async (body: SearchBody) => {
      const label = idempotencyKeyFor(body)

      // Pressing again without changing anything is not a new search. Sending it would be an
      // identical body within seconds of the last one, which the API counts as a duplicate job —
      // and cancelling the first to re-create it is worse, since a cancelled label is not replayed.
      if (started.current && label === startedLabel.current) return started.current

      if (started.current) {
        await endSearch(started.current.id)
        started.current = null
        startedLabel.current = null
      }

      const response = await fetch('/api/searches', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          accept: 'application/json',
          'idempotency-key': label,
        },
        body: JSON.stringify(body),
      })

      if (!response.ok) throw await HttpError.fromResponse(response)

      const search = (await response.json()) as Search
      started.current = search
      startedLabel.current = label
      return search
    },
    retry: false,
    // React Query hands the callback more than the job; the caller only wants the job.
    onSuccess: (search) => onStarted(search),
  })

  return mutation
}

async function endSearch(id: string): Promise<void> {
  try {
    await fetch(`/api/searches/${encodeURIComponent(id)}`, { method: 'DELETE' })
  } catch {
    // A slot that cannot be freed is the server's problem, not a reason to refuse the new search.
  }
}
