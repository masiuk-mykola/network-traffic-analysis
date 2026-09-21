'use client'

import * as RadixSelect from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'

import { cn } from '@lib/utils'

export type SelectOption = { value: string; label: string; group?: string }

type SelectProps = {
  value: string
  onValueChange: (value: string) => void
  options: readonly SelectOption[]
  placeholder: string
  disabled?: boolean
  id?: string
  'aria-label'?: string
  className?: string
}

export function Select({ options, placeholder, className, ...props }: SelectProps) {
  const groups = [...new Set(options.map((option) => option.group ?? ''))]

  return (
    <RadixSelect.Root {...props}>
      <RadixSelect.Trigger
        id={props.id}
        aria-label={props['aria-label']}
        className={cn(
          'border-border bg-surface/70 flex h-10 items-center justify-between gap-2 rounded-md border px-3 text-sm',
          'transition-[border-color,box-shadow] duration-150 ease-out',
          'hover:border-muted/60 focus-visible:border-accent focus-visible:ring-ring/40',
          'focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60',
          className,
        )}
      >
        <RadixSelect.Value placeholder={placeholder} />
        <ChevronDown aria-hidden className="text-muted size-4" />
      </RadixSelect.Trigger>

      <RadixSelect.Portal>
        <RadixSelect.Content
          position="popper"
          sideOffset={4}
          className="border-border bg-surface z-50 max-h-72 overflow-hidden rounded-md border shadow-xl"
        >
          <RadixSelect.Viewport className="p-1">
            {groups.map((group) => (
              <RadixSelect.Group key={group}>
                {group ? (
                  <RadixSelect.Label className="text-muted px-2 py-1 font-mono text-[0.65rem] tracking-wider uppercase">
                    {group}
                  </RadixSelect.Label>
                ) : null}
                {options
                  .filter((option) => (option.group ?? '') === group)
                  .map((option) => (
                    <RadixSelect.Item
                      key={option.value}
                      value={option.value}
                      className="data-[highlighted]:bg-accent/10 data-[highlighted]:text-foreground flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm outline-none"
                    >
                      <RadixSelect.ItemIndicator>
                        <Check aria-hidden className="text-accent size-3.5" />
                      </RadixSelect.ItemIndicator>
                      <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                    </RadixSelect.Item>
                  ))}
              </RadixSelect.Group>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  )
}
