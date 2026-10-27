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

/** Formats a duration in minutes as e.g. "2h 30 min", "1h" or "45 min". */
export function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours}h`)
  if (minutes > 0 || hours === 0) parts.push(`${minutes}${NBSP}min`)
  return parts.join(' ')
}

/** Describes a minimum free time for a sentence, e.g. "30 minutes",
 * "1 hour" or "2 hours". */
export function formatMinimumDuration(minutes: number): string {
  if (minutes === 60) return '1 hour'
  if (minutes % 60 === 0) return `${minutes / 60} hours`
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}
