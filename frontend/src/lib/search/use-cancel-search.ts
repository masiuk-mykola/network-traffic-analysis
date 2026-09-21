'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'

import { HttpError } from '@api/http-error'
import { searchKey } from '@api/keys'

import type { Search } from './search-state'

/**
 * Stops a running job and frees its slot. The cancelled state is written into the cache straight
 * away: the next poll is stopped by that ending, so a reply already in flight cannot flip the screen
 * back to "running".
 */
export function useCancelSearch(searchId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!searchId) return
      const response = await fetch(`/api/searches/${encodeURIComponent(searchId)}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw await HttpError.fromResponse(response)
    },
    retry: false,
    onSuccess: () => {
      if (!searchId) return
      queryClient.setQueryData<Search>(searchKey(searchId), (current) =>
        current ? { ...current, state: 'cancelled' } : current,
      )
    },
  })
}
