/** How far back the default window opens from the last traffic seen. */
export const WINDOW_HOURS = 6

/** The spans offered in one click, each ending at the same last traffic. */
export const WINDOW_PRESETS = [1, WINDOW_HOURS, 24] as const

const HOUR_MS = 60 * 60 * 1000

type Reporting = { last_packet_at?: string }

export type Window = { from: string; to: string }

/**
 * The traffic in this capture ends in the past, so a window built from the clock would return
 * nothing and look like a broken screen. The end is the latest moment any of the given points
 * reported; a point that is behind only earns a marker in the list, it does not shorten the window.
 */
export function defaultWindow(
  sensors: readonly Reporting[],
  hours: number = WINDOW_HOURS,
): Window | null {
  const latest = sensors
    .map((sensor) => (sensor.last_packet_at ? Date.parse(sensor.last_packet_at) : Number.NaN))
    .filter((value) => !Number.isNaN(value))
    .reduce((max, value) => (value > max ? value : max), Number.NEGATIVE_INFINITY)

  if (latest === Number.NEGATIVE_INFINITY) return null

  return {
    from: new Date(latest - hours * HOUR_MS).toISOString(),
    to: new Date(latest).toISOString(),
  }
}
