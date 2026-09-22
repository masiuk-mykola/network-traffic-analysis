'use client'

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { fetchJson } from '@api/fetch-json'
import { detectionsKey } from '@api/keys'
import type { components } from '@api/schema'

import { mergeDetections, type Detection } from './merge'
import type { FeedStatus } from './upstream-events'

type DetectionList = components['schemas']['DetectionList']

export type Feed = {
  detections: Detection[]
  status: FeedStatus
  /** Set when the server refused a resume point as too old, so the gap can be explained. */
  restarted: boolean
  seed: { isPending: boolean; error: unknown; refetch: () => void; isFetching: boolean }
}

/**
 * The feed as a screen sees it: what the server already held, plus what arrives while watching.
 *
 * The seed is an ordinary read through the proxy — the stream replays only on a resume, so a first
 * open would otherwise show an empty list until something happened to occur. The arrivals are
 * pushed rather than polled, so this is the one place in the app that holds server state outside
 * React Query: a query cannot represent something nobody asked for.
 */
export function useDetections(): Feed {
  const seed = useQuery({
    queryKey: detectionsKey(),
    // How many is the handler's business, not the screen's: it rations this read for everyone.
    queryFn: ({ signal }) => fetchJson<DetectionList>('detections', { signal }),
    // Pushed from here on; re-reading it would be asking for what the stream already delivers.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

  const [arrived, setArrived] = useState<Detection[]>([])
  const [status, setStatus] = useState<FeedStatus>('reconnecting')
  const [restarted, setRestarted] = useState(false)

  useEffect(() => {
    const source = new EventSource('/api/detections/stream')

    source.addEventListener('detection', (event) => {
      const detection = readJson<Detection>(event.data)
      if (detection) setArrived((held) => mergeDetections(held, [detection]))
    })

    source.addEventListener('reset', () => setRestarted(true))

    source.addEventListener('status', (event) => {
      const body = readJson<{ status?: FeedStatus }>(event.data)
      if (body?.status) setStatus(body.status)
    })

    // The browser retries this endpoint by itself, and reaching our own server costs the API
    // nothing — the one connection it grades is held on the other side of this handler.
    source.onerror = () => setStatus('reconnecting')

    return () => source.close()
  }, [])

  return {
    detections: mergeDetections(arrived, seed.data?.items ?? []),
    status,
    restarted,
    seed: {
      isPending: seed.isPending,
      error: seed.error,
      isFetching: seed.isFetching,
      refetch: () => void seed.refetch(),
    },
  }
}

function readJson<T>(data: unknown): T | null {
  if (typeof data !== 'string') return null
  try {
    return JSON.parse(data) as T
  } catch {
    return null
  }
}
