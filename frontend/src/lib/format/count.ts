import { EMPTY } from './empty'

const EXACT_BELOW = 1000
const SIGNIFICANT = 2

export function formatCount(value: number): string {
  if (!Number.isFinite(value) || value < 0) return EMPTY
  return new Intl.NumberFormat('en-GB').format(Math.round(value))
}

/**
 * An estimate should not read like a measurement. Below a thousand the server's number is small
 * enough to show as it is; above that it is rounded, so nobody quotes "12,431" from a sample.
 */
export function formatApproximate(value: number): string {
  if (!Number.isFinite(value) || value < 0) return EMPTY
  if (value < EXACT_BELOW) return formatCount(value)

  const magnitude = Math.floor(Math.log10(value)) - (SIGNIFICANT - 1)
  const step = 10 ** magnitude
  return formatCount(Math.round(value / step) * step)
}
