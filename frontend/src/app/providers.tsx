'use client'

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useRouter } from 'next/navigation'
import { useState, type ReactNode } from 'react'

import { safeRedirectTarget } from '@lib/auth/redirect-target'
import { createExpiryHandler, reportFailure, setExpiryHandler } from '@lib/auth/session-expiry'
import { retry, retryDelay } from '@lib/query-retry'
import { ToastProvider } from '@/components/toast/toast-provider'
import { useToast } from '@/components/toast/use-toast'

const SIGN_IN = '/login'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <QueryProvider>{children}</QueryProvider>
    </ToastProvider>
  )
}

/**
 * The query client is built inside the toast provider, because the one reaction to a dead session
 * lives here: every query and mutation failure passes through the caches' `onError`, so no screen
 * has to notice on its own.
 */
function QueryProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const { notify } = useToast()

  const [queryClient] = useState(() => {
    // Both paths report through the module, so there is one registered handler and one reaction
    // even when React mounts the tree twice in development.
    const onError = (error: unknown) => reportFailure(error)

    const client = new QueryClient({
      queryCache: new QueryCache({ onError }),
      mutationCache: new MutationCache({ onError }),
      defaultOptions: {
        queries: {
          staleTime: 30_000,
          gcTime: 5 * 60_000,
          refetchOnWindowFocus: false,
          retry,
          retryDelay,
        },
        mutations: { retry: false },
      },
    })

    const handler = createExpiryHandler({
      isSignedOut: () => window.location.pathname.startsWith(SIGN_IN),
      onExpired: () => {
        // Order matters: stop everything before leaving. A request that lands after the server
        // revoked the session is counted against us, and the window is five seconds.
        void client.cancelQueries()
        client.clear()
        notify({
          kind: 'error',
          title: 'Your session ended',
          detail: 'Sign in again to pick up where you left off.',
        })
        const next = safeRedirectTarget(window.location.pathname + window.location.search)
        router.replace(`${SIGN_IN}?next=${encodeURIComponent(next)}`)
      },
    })

    setExpiryHandler(handler)
    return client
  })

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
