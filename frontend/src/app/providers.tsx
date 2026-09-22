'use client'

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useRouter } from 'next/navigation'
import { useEffect, useState, type ReactNode } from 'react'

import { safeRedirectTarget } from '@lib/auth/redirect-target'
import { createExpiryHandler, reportFailure, setExpiryHandler } from '@lib/auth/session-expiry'
import { retry, retryDelay } from '@lib/query-retry'
import { ROUTES } from '@lib/routes'
import { ToastProvider } from '@/components/toast/toast-provider'
import { useToast } from '@/components/toast/use-toast'

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <QueryProvider>{children}</QueryProvider>
    </ToastProvider>
  )
}

function makeQueryClient(): QueryClient {
  // Both caches report through the module, so there is one registered handler and one reaction.
  const onError = (error: unknown) => reportFailure(error)

  return new QueryClient({
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
}

let browserClient: QueryClient | undefined

/**
 * One cache per browser, a fresh one per server render. A second client would be a second cache:
 * the same screen mounted twice would ask the API for everything twice, which the backend scores.
 */
function getQueryClient(): QueryClient {
  if (typeof window === 'undefined') return makeQueryClient()
  browserClient ??= makeQueryClient()
  return browserClient
}

/**
 * The provider sits inside the toast provider, because the one reaction to a dead session lives
 * here: every query and mutation failure passes through the caches' `onError`, so no screen has to
 * notice on its own.
 */
function QueryProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const { notify } = useToast()
  const [queryClient] = useState(getQueryClient)

  useEffect(() => {
    const handler = createExpiryHandler({
      isSignedOut: () => window.location.pathname.startsWith(ROUTES.signIn),
      onExpired: () => {
        // Order matters: stop everything before leaving. A request that lands after the server
        // revoked the session is counted against us, and the window is five seconds.
        void queryClient.cancelQueries()
        queryClient.clear()
        notify({
          kind: 'error',
          title: 'Your session ended',
          detail: 'Sign in again to pick up where you left off.',
        })
        const next = safeRedirectTarget(window.location.pathname + window.location.search)
        router.replace(`${ROUTES.signIn}?next=${encodeURIComponent(next)}`)
      },
    })

    setExpiryHandler(handler)
    return () => setExpiryHandler(null)
  }, [queryClient, notify, router])

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
