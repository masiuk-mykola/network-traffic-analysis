import { DetectionFeed } from './detection-feed'

/**
 * The live feed.
 *
 * A screen of its own rather than a panel on the search screen: the connection's lifetime is then a
 * question about one address, and nothing about the finished screens changes. The list itself is
 * read in the browser — it is pushed, not fetched, and a server render cannot represent something
 * that has not happened yet.
 */
export default function DetectionsPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Detections</h1>
        <p className="text-muted text-sm">
          What the capture points have flagged, as it happens. Newest first.
        </p>
      </div>

      <DetectionFeed />
    </main>
  )
}
