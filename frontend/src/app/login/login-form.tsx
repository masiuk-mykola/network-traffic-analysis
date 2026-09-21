'use client'

import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { useForm } from 'react-hook-form'

import { describeFailure } from '@api/failure'
import { credentialsSchema, type Credentials } from '@lib/auth/credentials'
import { useSignIn } from '@lib/auth/use-sign-in'
import { useCountdown } from '@lib/use-countdown'
import { ErrorState } from '@/components/states'
import { Field } from '@/components/form/field'
import { Button, Input } from '@/components/ui'

export function LoginForm({ destination }: { destination?: string }) {
  const signIn = useSignIn(destination)
  const failure = signIn.error ? describeFailure(signIn.error) : null
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Credentials>({
    resolver: zodResolver(credentialsSchema),
    mode: 'onSubmit',
    reValidateMode: 'onBlur',
    defaultValues: { email: '', password: '' },
  })

  return (
    <form
      noValidate
      onSubmit={handleSubmit((values) => signIn.mutate(values))}
      className="space-y-5"
    >
      <Field label="Email" error={errors.email?.message}>
        {(props) => (
          <Input
            {...props}
            {...register('email')}
            type="email"
            autoComplete="username"
            placeholder="you@company.example"
          />
        )}
      </Field>

      <Field label="Password" error={errors.password?.message}>
        {(props) => (
          <Input
            {...props}
            {...register('password')}
            type="password"
            autoComplete="current-password"
          />
        )}
      </Field>

      {/* Keyed by the failure, so a fresh refusal restarts the wait instead of inheriting a
          countdown that already reached zero. */}
      <SubmitButton
        key={failure?.id ?? 'first'}
        pending={signIn.isPending}
        waitMs={failure?.retryAfterMs ?? null}
      />

      {signIn.error ? <ErrorState error={signIn.error} className="min-h-0 py-2" /> : null}
    </form>
  )
}

/**
 * A disabled submit button also blocks implicit submission with Enter, so the whole form is held
 * back while the server is refusing attempts.
 */
function SubmitButton({ pending, waitMs }: { pending: boolean; waitMs: number | null }) {
  const waitSeconds = useCountdown(waitMs)

  return (
    <Button type="submit" disabled={pending || waitSeconds > 0} className="w-full">
      {pending ? <Loader2 aria-hidden className="size-4 animate-spin" /> : null}
      {label(pending, waitSeconds)}
    </Button>
  )
}

function label(pending: boolean, waitSeconds: number): string {
  if (pending) return 'Signing in'
  if (waitSeconds > 0) return `Try again in ${waitSeconds} s`
  return 'Sign in'
}
