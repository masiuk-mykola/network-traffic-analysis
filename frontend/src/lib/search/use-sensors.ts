'use client'

import { useQuery } from '@tanstack/react-query'

import { fetchJson } from '@api/fetch-json'
import { sensorsKey } from '@api/keys'
import type { components } from '@api/schema'

export type Sensor = components['schemas']['Sensor']
type SensorList = components['schemas']['SensorList']

/** The capture points this account may read. Rarely changes, so it is never polled. */
export function useSensors() {
  return useQuery({
    queryKey: sensorsKey(),
    queryFn: ({ signal }) => fetchJson<SensorList>('sensors', { signal }),
    staleTime: 5 * 60_000,
  })
}
