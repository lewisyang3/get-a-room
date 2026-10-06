import { apiBaseUrl } from '../config'
import { searchParams, type SearchRequest } from './availability'
import { fetchJson } from './http'

/** A building with at least one room free at the time searched. */
export type BuildingAvailability = {
  building_id: number
  building_code: string
  building_name: string
  /** How many of the building's rooms match the search. */
  free_rooms: number
  /** The latest time any of those rooms stays free until, `HH:MM` in the
   * term's timezone. */
  longest_free_until: string
  longest_free_minutes: number
  distance_meters: number | null
}

/** Every building with a room free, with the moment the API searched. */
export type BuildingAvailabilityList = {
  date: string | null
  day_of_week: number
  time: string
  results: BuildingAvailability[]
}

export function buildingAvailabilityUrl({
  baseUrl = apiBaseUrl,
  ...search
}: SearchRequest): string {
  return `${baseUrl}/availability/buildings?${searchParams(search)}`
}

function isBuildingAvailabilityList(
  value: unknown,
): value is BuildingAvailabilityList {
  if (typeof value !== 'object' || value === null) return false
  const list = value as Record<string, unknown>
  return typeof list.time === 'string' && Array.isArray(list.results)
}

/** Fetches how many rooms each building has free. Buildings with none are
 * left out. Throws an ApiError for a failed request, and rethrows the
 * AbortError when `signal` aborts it. */
export function fetchBuildingAvailability(
  request: SearchRequest,
): Promise<BuildingAvailabilityList> {
  return fetchJson(buildingAvailabilityUrl(request), {
    signal: request.signal,
    isValid: isBuildingAvailabilityList,
  })
}
