'use client'

import { formatApproximate, formatCount } from '@lib/format'
import { useEstimate } from '@lib/search/use-estimate'
import { ErrorState } from '@/components/states'

/**
 * How large this query is, shown where the decision to run it is made. While a new estimate is in
 * flight the old number is removed rather than dimmed: a number from the previous query is worse
 * than no number at all.
 */
export function EstimateLine({ params }: { params: URLSearchParams | null }) {
  const estimate = useEstimate(params)

  if (params === null) return null

  if (estimate.isError) {
    return <ErrorState error={estimate.error} className="min-h-0 py-2 text-left" />
  }

  if (estimate.isPending || estimate.isFetching) {
    return (
      <p role="status" aria-live="polite" className="text-muted text-sm">
        Estimating…
      </p>
    )
  }

  const { estimated_matches: matches, estimated_sessions_scanned: scanned } = estimate.data

  return (
    <div className="space-y-0.5">
      <p className="text-sm">
        {matches === 0 ? (
          'No sessions match this query'
        ) : (
          <>
            <span className="text-muted">≈</span> {formatApproximate(matches)} sessions match
          </>
        )}
      </p>
      <p className="text-muted text-xs">
        Estimated from a sample; the search would read about {formatCount(scanned)} sessions.
      </p>
    </div>
  )
}
