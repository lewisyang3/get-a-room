import type { SearchWhen } from './api/availability'

// A non-breaking space keeps a number with its unit, e.g. "2:30 PM".
const NBSP = ' '

/** Formats an `HH:MM` clock time as e.g. "2:30 PM". It's plain arithmetic,
 * so the device's timezone can't shift it. */
export function formatClockTime(value: string): string {
  const [hours, minutes] = value.split(':').map(Number)
  const suffix = hours < 12 ? 'AM' : 'PM'
  const hour12 = hours % 12 || 12
  return `${hour12}:${String(minutes).padStart(2, '0')}${NBSP}${suffix}`
}

/** Formats a duration in minutes as e.g. "2 h 30 min", "1 h" or "45 min". */
export function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours}${NBSP}h`)
  if (minutes > 0 || hours === 0) parts.push(`${minutes}${NBSP}min`)
  return parts.join(' ')
}

/** Describes a minimum free time for a sentence, e.g. "30 minutes",
 * "an hour" or "2 hours". */
export function formatMinimumDuration(minutes: number): string {
  if (minutes === 60) return 'an hour'
  if (minutes % 60 === 0) return `${minutes / 60} hours`
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}

/** Formats a `YYYY-MM-DD` date as e.g. "Mon, Oct 5". */
export function formatShortDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  // Formatting a UTC midnight in UTC keeps the calendar date as given.
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

/** Describes when a search looked: "now", or e.g. "at Mon, Oct 5, 2:30 PM".
 * The date and time come from the API's response, which is what it searched. */
export function formatSearchMoment(
  when: SearchWhen,
  page: { date: string | null; time: string },
): string {
  if (when.kind === 'now') return 'now'
  const time = formatClockTime(page.time)
  return page.date ? `at ${formatShortDate(page.date)}, ${time}` : `at ${time}`
}
