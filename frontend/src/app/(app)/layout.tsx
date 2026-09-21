import { headers } from 'next/headers'

import { requireProfile } from '@lib/auth/session'
import { AppHeader } from '@/components/app-header'

/**
 * The guard for every working screen: one identity call per navigation, before any protected
 * content is produced. Pages below this do not check again.
 */
export default async function AppLayout({ children }: LayoutProps<'/'>) {
  const destination = (await headers()).get('x-pathname') ?? '/search'
  const profile = await requireProfile(destination)

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <AppHeader profile={profile} />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  )
}
