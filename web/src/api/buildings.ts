import { apiBaseUrl } from '../config'
import { fetchJson } from './http'

/** A building that /availability searches. Coordinates are null until they're
 * filled in. */
export type Building = {
  building_id: number
  building_code: string
  building_name: string
  latitude: number | null
  longitude: number | null
}

type BuildingList = { results: Building[] }

export type BuildingsRequest = {
  signal?: AbortSignal
  baseUrl?: string
}

export function buildingsUrl(baseUrl: string = apiBaseUrl): string {
  return `${baseUrl}/buildings`
}

function isBuildingList(value: unknown): value is BuildingList {
  if (typeof value !== 'object' || value === null) return false
  return Array.isArray((value as Record<string, unknown>).results)
}

/** Fetches every searchable building, sorted by name. Throws an ApiError for
 * a failed request, and rethrows the AbortError when `signal` aborts it. */
export async function fetchBuildings({
  signal,
  baseUrl,
}: BuildingsRequest = {}): Promise<Building[]> {
  const list = await fetchJson(buildingsUrl(baseUrl), {
    signal,
    isValid: isBuildingList,
  })
  return list.results
}
