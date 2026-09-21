import { EMPTY } from './empty'

export type Endpoint = { ip: string; port: number; host?: string; country?: string }

export type FormattedEndpoint = {
  address: string
  /** Null when the API did not send one, so the caller renders nothing instead of an empty gap. */
  host: string | null
  country: string | null
}

export function formatEndpoint(value: Endpoint | null | undefined): FormattedEndpoint {
  if (!value) return { address: EMPTY, host: null, country: null }

  const ip = value.ip.includes(':') ? `[${value.ip}]` : value.ip
  return {
    address: `${ip}:${value.port}`,
    host: value.host ?? null,
    country: value.country ?? null,
  }
}
