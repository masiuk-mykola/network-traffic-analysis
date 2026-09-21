import 'server-only'

/** Server-side logging seam. Swap the sink here when a real logger arrives. */
export function logServerError(scope: string, detail: string): void {
  console.error(`[${scope}] ${detail}`)
}
