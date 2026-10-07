import { describe, expect, it } from 'vitest'
import {
  formatClockTime,
  formatDuration,
  formatMinimumDuration,
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

describe('formatMinimumDuration', () => {
  it.each([
    [30, '30 minutes'],
    [60, '1 hour'],
    [120, '2 hours'],
    [180, '3 hours'],
    [90, '90 minutes'],
    [1, '1 minute'],
  ])('describes %i minutes as %s', (minutes, expected) => {
    expect(formatMinimumDuration(minutes)).toBe(expected)
  })
})
