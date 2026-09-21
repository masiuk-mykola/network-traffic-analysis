import Link from 'next/link'

import type { Profile } from '@lib/auth/session'

import { SignOutButton } from './sign-out-button'

export function AppHeader({ profile }: { profile: Profile }) {
  return (
    <header className="border-border bg-surface/60 sticky top-0 z-10 border-b backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-6">
        <Link
          href="/search"
          className="focus-visible:ring-ring/60 rounded font-mono text-[0.7rem] tracking-[0.2em] uppercase focus-visible:ring-2 focus-visible:outline-none"
        >
          Capture
        </Link>

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
