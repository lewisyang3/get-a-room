import { describe, expect, it } from 'vitest'
import {
  formatClockTime,
  formatDistance,
  formatDuration,
  formatMinimumDuration,
  formatSearchMoment,
  formatShortDate,
  nextHalfHourInPacific,
} from './format'

// The formatters join numbers and units with non-breaking spaces.
const nbsp = (text: string) => text.replaceAll(' ', ' ')

describe('formatClockTime', () => {
  it.each([
    ['00:00', '12:00 AM'],
    ['07:05', '7:05 AM'],
    ['12:00', '12:00 PM'],
    ['14:30', '2:30 PM'],
    ['22:00', '10:00 PM'],
  ])('formats %s as %s', (value, expected) => {
    expect(formatClockTime(value)).toBe(nbsp(expected))
  })
})

describe('formatDuration', () => {
  it.each([
    [45, '45 min'],
    [60, '1 h'],
    [150, '2 h 30 min'],
    [0, '0 min'],
  ])('formats %i minutes as %s', (minutes, expected) => {
    expect(formatDuration(minutes)).toBe(expected.replace(/(\d) /g, '$1 '))
  })
})

describe('formatDistance', () => {
  it.each([
    [0, 'Under 0.1 mi'],
    [160, 'Under 0.1 mi'],
    [161, '0.1 mi'],
    [416, '0.3 mi'],
    [1609, '1.0 mi'],
    [24_000, '15 mi'],
  ])('formats %i m as %s', (meters, expected) => {
    expect(formatDistance(meters)).toBe(nbsp(expected))
  })
})

describe('formatMinimumDuration', () => {
  it.each([
    [30, '30 minutes'],
    [60, 'an hour'],
    [120, '2 hours'],
    [180, '3 hours'],
    [90, '90 minutes'],
    [1, '1 minute'],
  ])('describes %i minutes as %s', (minutes, expected) => {
    expect(formatMinimumDuration(minutes)).toBe(expected)
  })
})

describe('formatShortDate', () => {
  it('keeps the calendar date as given', () => {
    expect(formatShortDate('2026-10-05')).toBe('Mon, Oct 5')
  })
})

describe('formatSearchMoment', () => {
  const page = { date: '2026-10-05', time: '14:30' }

  it('says now for a now search', () => {
    expect(formatSearchMoment({ kind: 'now' }, page)).toBe('now')
  })

  it('names the date and time for a later search', () => {
    expect(
      formatSearchMoment({ kind: 'at', at: '2026-10-05T14:30' }, page),
    ).toBe(`at Mon, Oct 5, ${nbsp('2:30 PM')}`)
  })
})

describe('nextHalfHourInPacific', () => {
  it.each([
    // Standard time, UTC-8.
    ['2026-01-15T20:05:00Z', '2026-01-15T12:30'],
    // Daylight time, UTC-7, already on the half hour.
    ['2026-10-05T21:30:00Z', '2026-10-05T14:30'],
    // Rounds up to the hour.
    ['2026-10-05T21:31:00Z', '2026-10-05T15:00'],
    // The morning DST starts, just after the clocks jump from 2 to 3 a.m.
    ['2026-03-08T10:10:00Z', '2026-03-08T03:30'],
    // Rolls over midnight into the next day.
    ['2026-10-05T06:50:00Z', '2026-10-05T00:00'],
  ])('turns %s into %s', (now, expected) => {
    expect(nextHalfHourInPacific(new Date(now))).toBe(expected)
  })
})
