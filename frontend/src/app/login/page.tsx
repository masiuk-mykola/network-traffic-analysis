import { redirect } from 'next/navigation'

import { callApi } from '@api/server'
import { currentSessionId } from '@lib/session'

import { LoginForm } from './login-form'

const DEMO_ACCOUNTS = [
  { email: 'ana@quillmere.example', password: 'demo-analyst', role: 'sees everything' },
  { email: 'oli@quillmere.example', password: 'demo-observer', role: 'read-only' },
]

export default async function LoginPage() {
  if (await hasLiveSession()) redirect('/search')

  return (
    <main className="relative flex flex-1 items-center justify-center px-6 py-16">
      <div aria-hidden className="grid-backdrop pointer-events-none absolute inset-0" />

      <div className="relative w-full max-w-[26rem]">
        <header className="mb-8 space-y-3">
          <p className="text-muted font-mono text-[0.7rem] tracking-[0.2em] uppercase">
            Capture · traffic forensics
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Sign in</h1>
          <p className="text-muted text-sm">
            Three capture points, three days of traffic. Sign in to search it.
          </p>
        </header>

        <div className="border-border bg-surface/60 rounded-xl border p-6 shadow-[0_1px_0_0_var(--color-border)] backdrop-blur-sm">
          <LoginForm />
        </div>

        <section aria-label="Demo accounts" className="mt-6">
          <p className="text-muted mb-2 font-mono text-[0.7rem] tracking-[0.18em] uppercase">
            Demo environment
          </p>
          <ul className="border-border divide-border divide-y rounded-lg border">
            {DEMO_ACCOUNTS.map((account) => (
              <li key={account.email} className="flex items-baseline gap-2 px-3 py-2 text-xs">
                <code className="font-mono">{account.email}</code>
                <span className="text-border">/</span>
                <code className="text-accent font-mono">{account.password}</code>
                <span className="text-muted ml-auto">{account.role}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  )
}

/**
 * A cookie alone proves nothing: its session may be gone, and then every later call would fail.
 * The cookie is read outside the try on purpose — reading it is what marks this page dynamic, and
 * swallowing that signal would render the page as if nobody were ever signed in.
 */
async function hasLiveSession(): Promise<boolean> {
  const sessionId = await currentSessionId()
  if (!sessionId) return false

  try {
    await callApi({ path: '/v1/me' })
    return true
  } catch {
    return false
  }
}
