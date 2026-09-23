import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DateTimePicker, fromLocalInput, toLocalInput, withDay, withTime } from './date-time-picker'

const AT = '2025-10-27T06:27:30.000Z'

describe('the UTC conversions', () => {
  it('shows an instant as its UTC wall time, not the browser zone', () => {
    expect(toLocalInput(AT)).toBe('2025-10-27T06:27:30')
    expect(toLocalInput(null)).toBe('')
    expect(toLocalInput('not a time')).toBe('')
  })

  it('reads a wall time back as UTC', () => {
    expect(fromLocalInput('2025-10-27T06:27:30')).toBe(AT)
    expect(fromLocalInput('2025-10-27T06:27')).toBe('2025-10-27T06:27:00.000Z')
    expect(fromLocalInput('')).toBeNull()
    expect(fromLocalInput('garbage')).toBeNull()
  })
})

describe('changing one half of the moment', () => {
  it('moves to another day and keeps the time of day', () => {
    expect(withDay(AT, new Date('2025-10-03T00:00:00Z'))).toBe('2025-10-03T06:27:30.000Z')
  })

  it('starts a day at midnight when there was no time yet', () => {
    expect(withDay(null, new Date('2025-10-03T00:00:00Z'))).toBe('2025-10-03T00:00:00.000Z')
  })

  it('changes the time of day and keeps the day', () => {
    expect(withTime(AT, '23:05:09')).toBe('2025-10-27T23:05:09.000Z')
    expect(withTime(AT, '23:05')).toBe('2025-10-27T23:05:00.000Z')
  })

  it('ignores a time it cannot read, or one with no day to belong to', () => {
    expect(withTime(AT, '')).toBe(AT)
    expect(withTime(AT, '99:00')).toBe(AT)
    expect(withTime(null, '10:00')).toBeNull()
  })
})

describe('DateTimePicker', () => {
  it('still takes a typed moment', () => {
    const onChange = vi.fn()
    render(
      <DateTimePicker
        id="from"
        aria-label="From"
        calendarLabel="Pick the start"
        value={AT}
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2025-10-28T01:00' } })

    expect(onChange).toHaveBeenCalledWith('2025-10-28T01:00:00.000Z')
  })

  it('picks a day from the calendar and keeps the time', async () => {
    const onChange = vi.fn()
    render(
      <DateTimePicker
        id="from"
        aria-label="From"
        calendarLabel="Pick the start"
        value={AT}
        onChange={onChange}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Pick the start' }))
    await userEvent.click(await screen.findByRole('button', { name: /October 15th, 2025/ }))

    expect(onChange).toHaveBeenCalledWith('2025-10-15T06:27:30.000Z')
  })

  it('sets the time of day from the calendar', async () => {
    const onChange = vi.fn()
    render(
      <DateTimePicker
        id="from"
        aria-label="From"
        calendarLabel="Pick the start"
        value={AT}
        onChange={onChange}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Pick the start' }))
    fireEvent.change(await screen.findByLabelText('Time (UTC)'), { target: { value: '12:00:00' } })

    expect(onChange).toHaveBeenCalledWith('2025-10-27T12:00:00.000Z')
  })

  it('follows a value that arrives while the calendar is open', async () => {
    const props = { id: 'from', 'aria-label': 'From', calendarLabel: 'Pick the start' }
    const { rerender } = render(<DateTimePicker {...props} value={null} onChange={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: 'Pick the start' }))
    rerender(<DateTimePicker {...props} value={AT} onChange={vi.fn()} />)

    expect(await screen.findByRole('grid', { name: 'October 2025' })).toBeInTheDocument()
  })
})
