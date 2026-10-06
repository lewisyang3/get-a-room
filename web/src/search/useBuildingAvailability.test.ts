import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AvailabilityPage } from '../api/availability'
import type { SearchQuery } from './useAvailability'
import { useBuildingAvailability } from './useBuildingAvailability'

const NOW: SearchQuery = {
  when: { kind: 'now' },
  minimumMinutes: 60,
  buildingId: 2,
  text: 'dwin 242',
}

const PAGE: AvailabilityPage = {
  total: 0,
  limit: 50,
  offset: 0,
  date: '2026-10-05',
  day_of_week: 0,
  time: '14:30',
  results: [],
}

function counts(...pairs: [number, number][]) {
  return {
    date: '2026-10-05',
    day_of_week: 0,
    time: '14:30',
    results: pairs.map(([id, free]) => ({
      building_id: id,
      building_code: `B${id}`,
      building_name: `Building ${id}`,
      free_rooms: free,
      longest_free_until: '22:00',
      longest_free_minutes: 450,
      distance_meters: null,
    })),
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

/** Stubs fetch with responses that resolve only when the test says so. */
function controlledFetch() {
  const pending: {
    url: URL
    signal: AbortSignal | undefined
    resolve: (response: Response) => void
  }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(
      (url: string, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
          pending.push({
            url: new URL(url),
            signal: init?.signal ?? undefined,
            resolve,
          })
        }),
    ),
  )
  return pending
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useBuildingAvailability', () => {
  it('is unknown, and asks for nothing, without a search on screen', () => {
    const pending = controlledFetch()
    const { result } = renderHook(() => useBuildingAvailability(3, null, null))

    expect(result.current).toBe('unknown')
    expect(pending).toHaveLength(0)
  })

  it("counts every building at the list's exact moment", async () => {
    const pending = controlledFetch()
    const { result } = renderHook(() => useBuildingAvailability(3, NOW, PAGE))

    const params = pending[0].url.searchParams
    expect(pending[0].url.pathname).toBe('/availability/buildings')
    // Pinned to the minute the list shows, rather than "now" again.
    expect(params.get('at')).toBe('2026-10-05T14:30')
    // Every building, so the map can show them all.
    expect(params.has('building_id')).toBe(false)
    // The text search still applies.
    expect(params.get('building')).toBe('dwin')
    expect(params.get('room')).toBe('242')

    await act(async () => pending[0].resolve(jsonResponse(counts([1, 6]))))

    expect(result.current).toEqual(new Map([[1, 6]]))
  })

  it('keeps earlier counts while new ones load, and aborts stale ones', async () => {
    const pending = controlledFetch()
    const { result, rerender } = renderHook(
      ({ query }) => useBuildingAvailability(3, query, PAGE),
      { initialProps: { query: NOW } },
    )
    await act(async () => pending[0].resolve(jsonResponse(counts([1, 6]))))

    const next = { ...NOW, minimumMinutes: 120 }
    rerender({ query: next })
    expect(result.current).toEqual(new Map([[1, 6]]))

    rerender({ query: { ...next } })
    expect(pending[1].signal?.aborted).toBe(true)
    await act(async () => pending[2].resolve(jsonResponse(counts([1, 2]))))

    expect(result.current).toEqual(new Map([[1, 2]]))
  })

  it("doesn't ask again when only the page changes", () => {
    const pending = controlledFetch()
    const { rerender } = renderHook(
      ({ page }) => useBuildingAvailability(3, NOW, page),
      { initialProps: { page: PAGE } },
    )

    rerender({ page: { ...PAGE, offset: 50 } })

    expect(pending).toHaveLength(1)
  })

  it('becomes unknown when the counts fail', async () => {
    const pending = controlledFetch()
    const { result, rerender } = renderHook(
      ({ query }) => useBuildingAvailability(3, query, PAGE),
      { initialProps: { query: NOW } },
    )
    await act(async () => pending[0].resolve(jsonResponse(counts([1, 6]))))

    rerender({ query: { ...NOW } })
    await act(async () => pending[1].resolve(jsonResponse({}, 500)))

    expect(result.current).toBe('unknown')
  })
})
