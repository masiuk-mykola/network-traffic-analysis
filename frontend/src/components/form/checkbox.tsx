'use client'

import * as RadixCheckbox from '@radix-ui/react-checkbox'
import { Check } from 'lucide-react'

import { cn } from '@lib/utils'

type CheckboxProps = {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
  id?: string
  className?: string
}

export function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <RadixCheckbox.Root
      className={cn(
        'border-border data-[state=checked]:border-accent data-[state=checked]:bg-accent',
        'focus-visible:ring-ring/50 grid size-4 shrink-0 place-items-center rounded border',
        'transition-[background-color,border-color,box-shadow] duration-150 ease-out',
        'hover:border-muted focus-visible:ring-2 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <RadixCheckbox.Indicator>
        <Check aria-hidden className="text-accent-contrast size-3" strokeWidth={3} />
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  )
}
