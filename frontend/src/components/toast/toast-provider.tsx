'use client'

import * as Toast from '@radix-ui/react-toast'
import { X } from 'lucide-react'
import { createContext, useCallback, useMemo, useRef, useState, type ReactNode } from 'react'

import { describeFailure } from '@api/failure'
import { cn } from '@lib/utils'

export type ToastKind = 'error' | 'info'

export type ToastInput = {
  kind?: ToastKind
  title: string
  detail?: string
  code?: string | null
}

type Entry = ToastInput & { id: number; kind: ToastKind }

export type ToastApi = {
  notify: (input: ToastInput) => void
  /** Shorthand for reporting a failed call without repeating the wording on every screen. */
  notifyFailure: (error: unknown) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

const DURATION_MS = 6_000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<Entry[]>([])
  // A counter, not a timestamp: two toasts in the same millisecond must not share a key.
  const nextId = useRef(0)

  const notify = useCallback((input: ToastInput) => {
    setEntries((current) => [
      ...current,
      { ...input, kind: input.kind ?? 'info', id: (nextId.current += 1) },
    ])
  }, [])

  const notifyFailure = useCallback(
    (error: unknown) => {
      const failure = describeFailure(error)
      notify({ kind: 'error', title: failure.title, detail: failure.detail, code: failure.code })
    },
    [notify],
  )

  const dismiss = useCallback((id: number) => {
    setEntries((current) => current.filter((entry) => entry.id !== id))
  }, [])

  const api = useMemo(() => ({ notify, notifyFailure }), [notify, notifyFailure])

  return (
    <ToastContext.Provider value={api}>
      <Toast.Provider duration={DURATION_MS} swipeDirection="right">
        {children}
        {entries.map((entry) => (
          <Toast.Root
            key={entry.id}
            onOpenChange={(open) => {
              if (!open) dismiss(entry.id)
            }}
            className={cn(
              'border-border bg-background flex items-start gap-3 rounded border p-3 shadow-lg',
              entry.kind === 'error' && 'border-danger',
            )}
          >
            <div className="space-y-1">
              <Toast.Title className="text-sm font-medium">{entry.title}</Toast.Title>
              {entry.detail ? (
                <Toast.Description className="text-muted text-sm">{entry.detail}</Toast.Description>
              ) : null}
              {entry.code ? <p className="text-muted text-xs">{entry.code}</p> : null}
            </div>
            <Toast.Close aria-label="Dismiss" className="text-muted hover:text-foreground ml-auto">
              <X aria-hidden className="size-4" />
            </Toast.Close>
          </Toast.Root>
        ))}
        <Toast.Viewport
          label="Notifications"
          className="fixed right-4 bottom-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
        />
      </Toast.Provider>
    </ToastContext.Provider>
  )
}
