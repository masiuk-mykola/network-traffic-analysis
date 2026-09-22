import Link from 'next/link'

import type { Profile } from '@lib/auth/session'
import { ROUTES } from '@lib/routes'

import { SignOutButton } from './sign-out-button'

const NAV = [
  { href: ROUTES.search, label: 'Search' },
  { href: ROUTES.detections, label: 'Detections' },
] as const

export function AppHeader({ profile }: { profile: Profile }) {
  return (
    <header className="border-border bg-surface/60 sticky top-0 z-10 border-b backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-6">
        <Link
          href={ROUTES.search}
          className="focus-visible:ring-ring/60 rounded font-mono text-[0.7rem] tracking-[0.2em] uppercase focus-visible:ring-2 focus-visible:outline-none"
        >
          Capture
        </Link>

        <nav aria-label="Main" className="flex items-center gap-3">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              // Not prefetched: a prefetch runs the guard's own identity read for a screen nobody
              // has asked for, on every page view, and the API counts identical reads.
              prefetch={false}
              className="focus-visible:ring-ring/60 text-muted hover:text-foreground rounded text-sm focus-visible:ring-2 focus-visible:outline-none"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm">{profile.display_name}</span>
          <span className="border-border text-muted rounded-full border px-2 py-0.5 font-mono text-[0.65rem] tracking-wider uppercase">
            {profile.role}
          </span>
          <SignOutButton />
        </div>
      </div>
    </header>
  )
}
