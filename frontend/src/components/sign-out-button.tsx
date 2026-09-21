'use client'

import * as Dialog from '@radix-ui/react-dialog'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { useState } from 'react'

import { Button } from '@/components/ui'

export function SignOutButton() {
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const queryClient = useQueryClient()
  const router = useRouter()

  async function signOut() {
    setPending(true)
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } finally {
      // Cancel and drop everything first: anything still in flight would otherwise land on a
      // session the server has already revoked, which the API counts against us.
      await queryClient.cancelQueries()
      queryClient.clear()
      setPending(false)
      setOpen(false)
      router.replace('/login')
      router.refresh()
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="ghost" size="sm">
          Sign out
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-[1px]" />
        <Dialog.Content className="border-border bg-surface fixed top-1/2 left-1/2 w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border p-5 shadow-xl">
          <Dialog.Title className="text-base font-medium">Sign out?</Dialog.Title>
          <Dialog.Description className="text-muted mt-1 text-sm">
            Anything running will be dropped, and you will need to sign in again.
          </Dialog.Description>

          <div className="mt-5 flex justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="secondary" size="sm">
                Stay signed in
              </Button>
            </Dialog.Close>
            <Button size="sm" disabled={pending} onClick={() => void signOut()}>
              {pending ? 'Signing out' : 'Sign out'}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
