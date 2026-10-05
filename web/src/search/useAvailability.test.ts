import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AvailabilityPage, AvailabilityResult } from '../api/availability'
import { useAvailability, type SearchQuery } from './useAvailability'

function room(id: number): AvailabilityResult {
  return {
    room_id: id,
    building_id: 1,
    building_code: 'DWINELLE',
    building_name: 'Dwinelle',
    room_number: String(100 + id),
    available_from: '14:30',
    available_until: '17:00',
    available_minutes: 150,
  }
}

function page(ids: number[], total = ids.length, offset = 0): AvailabilityPage {
  return {
    total,
    limit: 50,
    offset,
    date: '2026-10-05',
    day_of_week: 0,
    time: '14:30',
    results: ids.map(room),
  }
}

const NOW: SearchQuery = {
  when: { kind: 'now' },
  minimumMinutes: 60,
  buildingId: null,
  text: '',
}

function at(value: string, minimumMinutes = 60): SearchQuery {
  return {
    when: { kind: 'at', at: value },
    minimumMinutes,
    buildingId: null,
    text: '',
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

/** Stubs fetch with responses that resolve only when the test says so. */
function controlledFetch() {
  const pending: {
    url: string
    signal: AbortSignal | undefined
    resolve: (response: Response) => void
  }[] = []
  const fetchMock = vi.fn(
    (url: string, init?: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        )
        pending.push({ url, signal: init?.signal ?? undefined, resolve })
      }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, pending }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useAvailability', () => {
  it('loads a search and keeps the results', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    expect(result.current.status).toBe('loading')

    await act(async () => pending[0].resolve(jsonResponse(page([1, 2]))))

    expect(result.current.status).toBe('success')
    expect(result.current.results.map((r) => r.room_id)).toEqual([1, 2])
    expect(result.current.page?.total).toBe(2)
  })

  it('aborts the previous search and ignores its response', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    act(() => {
      void result.current.search(at('2026-10-05T15:00'))
    })

    expect(pending[0].signal?.aborted).toBe(true)
    await act(async () => pending[1].resolve(jsonResponse(page([9]))))

    expect(result.current.query).toEqual(at('2026-10-05T15:00'))
    expect(result.current.results.map((r) => r.room_id)).toEqual([9])
  })

  it('keeps earlier results visible while a new search loads', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1]))))
    act(() => {
      void result.current.search(NOW)
    })

    expect(result.current.status).toBe('loading')
    expect(result.current.results.map((r) => r.room_id)).toEqual([1])
  })

  it('reports an error and clears results from the earlier search', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1]))))
    act(() => {
      void result.current.search(NOW)
    })
    await act(async () =>
      pending[1].resolve(jsonResponse({ detail: 'x' }, 404)),
    )

    expect(result.current.status).toBe('error')
    expect(result.current.error?.kind).toBe('not-found')
    expect(result.current.results).toEqual([])
  })

  it('retries the last search', async () => {
    const { fetchMock, pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(at('2026-10-05T14:30'))
    })
    await act(async () => pending[0].resolve(jsonResponse({}, 500)))
    act(() => result.current.retry())
    await act(async () => pending[1].resolve(jsonResponse(page([4]))))

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(pending[1].url).toContain('at=2026-10-05T14%3A30')
    expect(result.current.status).toBe('success')
  })

  it('appends the next page', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1, 2], 3))))
    act(() => {
      void result.current.loadMore()
    })

    expect(result.current.loadingMore).toBe(true)
    expect(pending[1].url).toContain('offset=2')
    await act(async () => pending[1].resolve(jsonResponse(page([3], 3, 2))))

    expect(result.current.loadingMore).toBe(false)
    expect(result.current.results.map((r) => r.room_id)).toEqual([1, 2, 3])
  })

  it("pins later pages of a now search to the first page's moment", async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () =>
      pending[0].resolve(
        jsonResponse({ ...page([1, 2], 3), date: '2026-10-05', time: '13:59' }),
      ),
    )
    act(() => {
      void result.current.loadMore()
    })

    const url = new URL(pending[1].url)
    expect(url.searchParams.get('at')).toBe('2026-10-05T13:59')
    expect(url.searchParams.get('offset')).toBe('2')
    // The results are still described as a now search.
    expect(result.current.query).toEqual(NOW)
  })

  it('keeps the filters when loading more and retrying', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))
    const query: SearchQuery = {
      when: { kind: 'now' },
      minimumMinutes: 120,
      buildingId: 4,
      text: 'Dwinelle 242',
    }

    act(() => {
      void result.current.search(query)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1], 3))))
    act(() => {
      void result.current.loadMore()
    })
    const more = new URL(pending[1].url)
    expect(more.searchParams.get('minimum_minutes')).toBe('120')
    expect(more.searchParams.get('building_id')).toBe('4')
    expect(more.searchParams.get('building')).toBe('Dwinelle')
    expect(more.searchParams.get('room')).toBe('242')
    expect(more.searchParams.get('at')).toBe('2026-10-05T14:30')

    await act(async () => pending[1].resolve(jsonResponse({}, 500)))
    act(() => {
      void result.current.search(query)
    })
    await act(async () => pending[2].resolve(jsonResponse({}, 503)))
    act(() => result.current.retry())

    const retried = new URL(pending[3].url)
    expect(retried.searchParams.get('minimum_minutes')).toBe('120')
    expect(retried.searchParams.get('building_id')).toBe('4')
    expect(retried.searchParams.get('building')).toBe('Dwinelle')
    expect(retried.searchParams.get('room')).toBe('242')
  })

  it('skips rooms already listed when appending a page', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1, 2], 4))))
    act(() => {
      void result.current.loadMore()
    })
    await act(async () => pending[1].resolve(jsonResponse(page([2, 3], 4, 2))))

    expect(result.current.results.map((r) => r.room_id)).toEqual([1, 2, 3])
  })

  it('keeps loaded rooms when loading more fails', async () => {
    const { pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1], 2))))
    act(() => {
      void result.current.loadMore()
    })
    await act(async () => pending[1].resolve(jsonResponse({}, 500)))

    expect(result.current.status).toBe('success')
    expect(result.current.results.map((r) => r.room_id)).toEqual([1])
    expect(result.current.loadMoreError?.kind).toBe('server')
  })

  it('does nothing when every room is loaded', async () => {
    const { fetchMock, pending } = controlledFetch()
    const { result } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    await act(async () => pending[0].resolve(jsonResponse(page([1]))))
    act(() => {
      void result.current.loadMore()
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('aborts the request in flight on unmount', () => {
    const { pending } = controlledFetch()
    const { result, unmount } = renderHook(() => useAvailability(3))

    act(() => {
      void result.current.search(NOW)
    })
    unmount()

    expect(pending[0].signal?.aborted).toBe(true)
  })
})
