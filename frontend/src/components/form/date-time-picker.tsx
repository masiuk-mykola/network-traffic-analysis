'use client'

import * as Popover from '@radix-ui/react-popover'
import { CalendarDays } from 'lucide-react'
import { useId } from 'react'
import { DayPicker } from 'react-day-picker'

import { Input } from '@/components/ui'
import { cn } from '@lib/utils'

const TIME = /^(\d{2}):(\d{2})(?::(\d{2}))?$/
const MAX_HOUR = 23
const MAX_MINUTE = 59

type DateTimePickerProps = {
  id: string
  /**
   * Names the calendar button. It must not repeat the field's own label, or a lookup by that label
   * finds the button as well as the field.
   */
  calendarLabel: string
  /** An ISO instant; the control shows and edits it as UTC wall time. */
  value: string | null
  onChange: (value: string | null) => void
  'aria-invalid'?: boolean
  'aria-describedby'?: string
  'aria-label'?: string
}

/**
 * A moment in UTC: typed into the field, or picked from a calendar that speaks UTC too. The
 * browser's own picker is hidden because it speaks the browser's zone and ignores the theme.
 */
export function DateTimePicker({
  calendarLabel,
  value,
  onChange,
  ...inputProps
}: DateTimePickerProps) {
  const timeId = useId()
  const selected = parse(value)

  return (
    <div className="relative">
      <Input
        {...inputProps}
        type="datetime-local"
        step="1"
        value={toLocalInput(value)}
        onChange={(event) => onChange(fromLocalInput(event.target.value))}
        className="pr-11 [&::-webkit-calendar-picker-indicator]:hidden"
      />
      <Popover.Root>
        <Popover.Trigger
          type="button"
          aria-label={calendarLabel}
          className={cn(
            'text-muted hover:text-foreground hover:bg-foreground/5 absolute top-1 right-1 grid size-8 place-items-center rounded',
            'focus-visible:ring-ring/60 focus-visible:ring-2 focus-visible:outline-none',
          )}
        >
          <CalendarDays aria-hidden className="size-4" />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            align="end"
            sideOffset={6}
            className="border-border bg-surface z-50 space-y-3 rounded-md border p-3 shadow-xl"
          >
            <DayPicker
              // The calendar keeps its own month once shown; a value that moves to another month
              // (a preset, a typed date, a window that arrived late) has to bring the view along.
              key={toLocalInput(value).slice(0, 7)}
              mode="single"
              timeZone="UTC"
              selected={selected ?? undefined}
              defaultMonth={selected ?? undefined}
              onSelect={(day) => {
                if (day) onChange(withDay(value, day))
              }}
              classNames={CALENDAR_CLASSES}
            />
            <div className="border-border flex items-center justify-between gap-3 border-t pt-3">
              <label htmlFor={timeId} className="text-muted text-xs">
                Time (UTC)
              </label>
              <Input
                id={timeId}
                type="time"
                step="1"
                disabled={!selected}
                value={toLocalInput(value).slice(11)}
                onChange={(event) => onChange(withTime(value, event.target.value))}
                className="h-8 w-32 font-mono"
              />
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  )
}

const CALENDAR_CLASSES = {
  months: 'relative',
  month_caption: 'flex h-8 items-center px-1 text-sm font-medium',
  nav: 'absolute top-0 right-0 flex gap-1',
  button_previous:
    'text-muted hover:text-foreground hover:bg-foreground/5 grid size-8 place-items-center rounded disabled:opacity-40',
  button_next:
    'text-muted hover:text-foreground hover:bg-foreground/5 grid size-8 place-items-center rounded disabled:opacity-40',
  chevron: 'size-4 fill-current',
  month_grid: 'mt-2 border-collapse',
  weekday: 'text-muted size-9 text-center font-mono text-[0.65rem] font-normal uppercase',
  day: 'size-9 p-0 text-center text-sm',
  day_button:
    'hover:bg-accent/10 size-9 rounded tabular-nums focus-visible:ring-ring/60 focus-visible:ring-2 focus-visible:outline-none',
  selected: '[&>button]:bg-accent [&>button]:text-accent-contrast [&>button]:hover:bg-accent',
  today: 'text-accent font-semibold',
  outside: 'text-muted/50',
} as const

function parse(iso: string | null): Date | null {
  if (!iso) return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `datetime-local` speaks the browser's zone; everything here is UTC, so convert explicitly. */
export function toLocalInput(iso: string | null): string {
  const date = parse(iso)
  return date ? date.toISOString().slice(0, 19) : ''
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null
  const parsed = Date.parse(`${value}Z`)
  return Number.isNaN(parsed) ? null : new Date(parsed).toISOString()
}

/** The calendar hands back a UTC midnight; the time of day already chosen is kept. */
export function withDay(iso: string | null, day: Date): string {
  const current = parse(iso)
  const next = new Date(
    Date.UTC(
      day.getUTCFullYear(),
      day.getUTCMonth(),
      day.getUTCDate(),
      current?.getUTCHours() ?? 0,
      current?.getUTCMinutes() ?? 0,
      current?.getUTCSeconds() ?? 0,
    ),
  )
  return next.toISOString()
}

export function withTime(iso: string | null, time: string): string | null {
  const current = parse(iso)
  const match = TIME.exec(time)
  if (!current || !match) return iso
  const hours = Number(match[1])
  const minutes = Number(match[2])
  const seconds = Number(match[3] ?? 0)
  if (hours > MAX_HOUR || minutes > MAX_MINUTE || seconds > MAX_MINUTE) return iso
  const next = new Date(current)
  next.setUTCHours(hours, minutes, seconds, 0)
  return next.toISOString()
}
