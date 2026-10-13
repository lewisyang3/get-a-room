import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildingsUrl, fetchBuildings, type Building } from './buildings'
import { ApiError } from './http'

const BUILDINGS: Building[] = [
  {
    building_id: 2,
    building_code: 'DWINELLE',
    building_name: 'Dwinelle',
    latitude: null,
    longitude: null,
  },
  {
    building_id: 3,
    building_code: 'EVANS',
    building_name: 'Evans',
    latitude: null,
    longitude: null,
  },
]

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

describe('buildingsUrl', () => {
  it('appends the path to the base URL', () => {
    expect(buildingsUrl('https://api.example.com')).toBe(
      'https://api.example.com/buildings',
    )
  })
})

describe('fetchBuildings', () => {
  it('returns the buildings', async () => {
    const fetchMock = stubFetch(async () =>
      jsonResponse({ results: BUILDINGS }),
    )

    await expect(
      fetchBuildings({ baseUrl: 'https://api.example.com' }),
    ).resolves.toEqual(BUILDINGS)
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.com/buildings',
      expect.anything(),
    )
  })

  it('reports an error status', async () => {
    stubFetch(async () => jsonResponse({ detail: 'nope' }, 503))

    const error = await rejection(fetchBuildings())
    expect(error.kind).toBe('server')
    expect(error.status).toBe(503)
  })

  it('reports a failed connection as a network error', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    const error = await rejection(fetchBuildings())
    expect(error.kind).toBe('network')
  })

  it('reports invalid JSON as a server error', async () => {
    stubFetch(async () => new Response('<html>', { status: 200 }))

    const error = await rejection(fetchBuildings())
    expect(error.kind).toBe('server')
  })

  it('reports an unexpected body as a server error', async () => {
    stubFetch(async () => jsonResponse(BUILDINGS))

    const error = await rejection(fetchBuildings())
    expect(error.kind).toBe('server')
  })

  it('rethrows an abort instead of reporting a network error', async () => {
    const controller = new AbortController()
    stubFetch(async () => {
      controller.abort()
      throw new DOMException('Aborted', 'AbortError')
    })

    await expect(
      fetchBuildings({ signal: controller.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' })
  })
})
