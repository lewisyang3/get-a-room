import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildingAvailabilityUrl,
  fetchBuildingAvailability,
  type BuildingAvailabilityList,
} from './buildingAvailability'
import { ApiError } from './http'

const LIST: BuildingAvailabilityList = {
  date: '2026-10-05',
  day_of_week: 0,
  time: '14:30',
  results: [
    {
      building_id: 2,
      building_code: 'DWINELLE',
      building_name: 'Dwinelle',
      free_rooms: 6,
      longest_free_until: '22:00',
      longest_free_minutes: 450,
      distance_meters: null,
    },
  ],
}

const SEARCH = {
  termId: 3,
  when: { kind: 'now' } as const,
  minimumMinutes: 60,
  buildingId: null,
  building: null,
  room: null,
  baseUrl: 'https://api.example.com',
}

function stubFetch(implementation: () => Promise<Response>) {
  const fetchMock = vi.fn(implementation)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('buildingAvailabilityUrl', () => {
  it('sends the search without paging', () => {
    const url = new URL(
      buildingAvailabilityUrl({
        ...SEARCH,
        when: { kind: 'at', at: '2026-10-05T14:30' },
        building: 'dwin',
        room: '242',
      }),
    )

    expect(url.origin + url.pathname).toBe(
      'https://api.example.com/availability/buildings',
    )
    expect(Object.fromEntries(url.searchParams)).toEqual({
      term_id: '3',
      at: '2026-10-05T14:30',
      minimum_minutes: '60',
      building: 'dwin',
      room: '242',
    })
  })

  it('leaves out the time for a search right now', () => {
    const url = new URL(buildingAvailabilityUrl(SEARCH))

    expect(url.searchParams.has('at')).toBe(false)
  })
})

describe('fetchBuildingAvailability', () => {
  it('returns the counts', async () => {
    stubFetch(async () => jsonResponse(LIST))

    await expect(fetchBuildingAvailability(SEARCH)).resolves.toEqual(LIST)
  })

  it('rejects an unexpected response', async () => {
    stubFetch(async () => jsonResponse({ results: 'nope' }))

    await expect(fetchBuildingAvailability(SEARCH)).rejects.toBeInstanceOf(
      ApiError,
    )
  })
})
