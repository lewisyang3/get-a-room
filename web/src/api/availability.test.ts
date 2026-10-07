import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  availabilityUrl,
  fetchAvailability,
  type AvailabilityPage,
} from './availability'
import { ApiError } from './http'

const PAGE: AvailabilityPage = {
  total: 1,
  limit: 50,
  offset: 0,
  date: '2026-10-05',
  day_of_week: 0,
  time: '14:30',
  results: [
    {
      room_id: 7,
      building_id: 2,
      building_code: 'DWINELLE',
      building_name: 'Dwinelle',
      room_number: '242',
      available_from: '14:30',
      available_until: '17:00',
      available_minutes: 150,
      distance_meters: null,
    },
  ],
}

function stubFetch(implementation: () => Promise<Response>) {
  const fetchMock = vi.fn(implementation)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiError) return error
    throw error
  }
  throw new Error('Expected the request to fail')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('availabilityUrl', () => {
  it('searches now by leaving out the time parameters', () => {
    const url = new URL(
      availabilityUrl({
        termId: 3,
        minimumMinutes: 60,
        buildingId: null,
        building: null,
        room: null,
        baseUrl: 'http://api.test',
      }),
    )

    expect(url.origin + url.pathname).toBe('http://api.test/availability')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      term_id: '3',
      minimum_minutes: '60',
      limit: '50',
      offset: '0',
    })
  })

  it('passes a pinned time as at, with the filters and paging', () => {
    const url = new URL(
      availabilityUrl({
        termId: 3,
        at: '2026-10-05T14:30',
        minimumMinutes: 120,
        buildingId: 4,
        building: 'Dwinelle Hall',
        room: '242',
        offset: 50,
        baseUrl: 'http://api.test',
      }),
    )

    expect(url.searchParams.get('at')).toBe('2026-10-05T14:30')
    expect(url.searchParams.get('minimum_minutes')).toBe('120')
    expect(url.searchParams.get('building_id')).toBe('4')
    expect(url.searchParams.get('building')).toBe('Dwinelle Hall')
    expect(url.searchParams.get('room')).toBe('242')
    expect(url.searchParams.get('offset')).toBe('50')
  })
})

describe('fetchAvailability', () => {
  const request = {
    termId: 3,
    minimumMinutes: 60,
    buildingId: null,
    building: null,
    room: null,
  }

  it('returns the page', async () => {
    stubFetch(async () => jsonResponse(PAGE))

    await expect(fetchAvailability(request)).resolves.toEqual(PAGE)
  })

  it.each([
    [404, 'not-found'],
    [422, 'invalid'],
    [500, 'server'],
    [503, 'server'],
  ])('reports a %i as %s', async (status, kind) => {
    stubFetch(async () => jsonResponse({ detail: 'nope' }, status))

    const error = await rejection(fetchAvailability(request))
    expect(error.kind).toBe(kind)
    expect(error.status).toBe(status)
  })

  it('reports a failed connection as a network error', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    const error = await rejection(fetchAvailability(request))
    expect(error.kind).toBe('network')
  })

  it('reports invalid JSON as a server error', async () => {
    stubFetch(async () => new Response('<html>', { status: 200 }))

    const error = await rejection(fetchAvailability(request))
    expect(error.kind).toBe('server')
  })

  it('reports an unexpected body as a server error', async () => {
    stubFetch(async () => jsonResponse({ rooms: [] }))

    const error = await rejection(fetchAvailability(request))
    expect(error.kind).toBe('server')
  })

  it('rethrows an abort instead of reporting a network error', async () => {
    const controller = new AbortController()
    stubFetch(async () => {
      controller.abort()
      throw new DOMException('Aborted', 'AbortError')
    })

    await expect(
      fetchAvailability({ ...request, signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' })
  })
})
