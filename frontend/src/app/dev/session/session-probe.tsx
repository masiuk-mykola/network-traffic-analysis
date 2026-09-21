'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { ErrorState, LoadingState } from '@/components/states'
import { Button } from '@/components/ui'

type Profile = { display_name: string; role: string }

export function SessionProbe() {
  const me = useQuery({
    queryKey: ['me'] as const,
    queryFn: ({ signal }) => fetchJson<Profile>('me', { signal }),
    retry: false,
  })

  if (me.isPending) return <LoadingState label="Loading profile" />
  if (me.isError) return <ErrorState error={me.error} onRetry={() => void me.refetch()} />

  return (
    <div className="space-y-3">
      <p data-testid="probe-name">{me.data.display_name}</p>
      <Button variant="secondary" size="sm" onClick={() => void me.refetch()}>
        Read again
      </Button>
    </div>
  )
}
