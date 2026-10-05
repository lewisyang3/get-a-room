import { apiBaseUrl } from '../config'
import { fetchJson } from './http'

/** A room with no scheduled class at the time searched. Times are `HH:MM` in
 * the term's timezone. */
export type AvailabilityResult = {
  room_id: number
  building_id: number
  building_code: string
  building_name: string
  room_number: string
  available_from: string
  available_until: string
  available_minutes: number
}

/** One page of rooms, with the date, weekday and time the API searched. */
export type AvailabilityPage = {
  total: number
  limit: number
  offset: number
  /** The local date searched, `YYYY-MM-DD`. */
  date: string | null
  day_of_week: number
  time: string
  results: AvailabilityResult[]
}

/** When to search: right now, or at a Pacific clock time
 * (`YYYY-MM-DDTHH:MM`, no UTC offset). */
export type SearchWhen = { kind: 'now' } | { kind: 'at'; at: string }

export const PAGE_SIZE = 50

/** The API's default minimum free time, in minutes. */
export const DEFAULT_MINIMUM_MINUTES = 60

/** The minimum free times a student can choose, in minutes. */
export const MINIMUM_MINUTES_OPTIONS = [30, 60, 120, 180] as const

export type AvailabilityRequest = {
  termId: number
  when: SearchWhen
  /** Only rooms free for at least this many minutes. */
  minimumMinutes: number
  /** Only rooms in this building, or every building when null. */
  buildingId: number | null
  /** Only rooms in buildings whose name contains this text. */
  building: string | null
  /** Only rooms with exactly this room number. */
  room: string | null
  offset?: number
  limit?: number
  signal?: AbortSignal
  baseUrl?: string
}

export function availabilityUrl({
  termId,
  when,
  minimumMinutes,
  buildingId,
  building,
  room,
  offset = 0,
  limit = PAGE_SIZE,
  baseUrl = apiBaseUrl,
}: AvailabilityRequest): string {
  const params = new URLSearchParams({ term_id: String(termId) })
  // With no time parameters the API searches right now, on its own clock.
  if (when.kind === 'at') params.set('at', when.at)
  params.set('minimum_minutes', String(minimumMinutes))
  if (buildingId !== null) params.set('building_id', String(buildingId))
  if (building !== null) params.set('building', building)
  if (room !== null) params.set('room', room)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return `${baseUrl}/availability?${params}`
}

function isAvailabilityPage(value: unknown): value is AvailabilityPage {
  if (typeof value !== 'object' || value === null) return false
  const page = value as Record<string, unknown>
  return (
    typeof page.total === 'number' &&
    typeof page.time === 'string' &&
    Array.isArray(page.results)
  )
}

/** Fetches one page of available rooms. Throws an ApiError for a failed
 * request, and rethrows the AbortError when `signal` aborts it. */
export function fetchAvailability(
  request: AvailabilityRequest,
): Promise<AvailabilityPage> {
  return fetchJson(availabilityUrl(request), {
    signal: request.signal,
    isValid: isAvailabilityPage,
  })
}
