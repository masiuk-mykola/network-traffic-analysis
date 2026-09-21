import { useId, type ReactNode } from 'react'

import { cn } from '@lib/utils'

type FieldProps = {
  label: string
  /** Rendered under the label; also announced, because it is tied to the control. */
  description?: string
  error?: string
  className?: string
  /** Receives the ids the label and the messages were bound to. */
  children: (props: {
    id: string
    'aria-invalid': boolean
    'aria-describedby': string | undefined
  }) => ReactNode
}

/** Label, control and messages bound together, so no form has to remember how to do it. */
export function Field({ label, description, error, className, children }: FieldProps) {
  const id = useId()
  const descriptionId = description ? `${id}-description` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [descriptionId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {description ? (
        <p id={descriptionId} className="text-muted text-xs">
          {description}
        </p>
      ) : null}
      {children({ id, 'aria-invalid': Boolean(error), 'aria-describedby': describedBy })}
      {error ? (
        <p id={errorId} className="text-danger text-sm">
          {error}
        </p>
      ) : null}
    </div>
  )
}
