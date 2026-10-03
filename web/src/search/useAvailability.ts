import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  fetchAvailability,
  type AvailabilityPage,
  type AvailabilityResult,
  type SearchWhen,
} from '../api/availability'

/** What to search for: when, and how long a room must stay free. */
export type SearchQuery = {
  when: SearchWhen
  minimumMinutes: number
}

export type AvailabilityState = {
  status: 'idle' | 'loading' | 'success' | 'error'
  /** The latest search requested, which is loading, shown or failed. */
  query: SearchQuery | null
  /** The search that produced `page` and `results`. While a new search
   * loads, it still describes the results on screen. */
  resultsQuery: SearchQuery | null
  /** The latest page, for the total and the moment the API searched. */
  page: AvailabilityPage | null
  /** Every room loaded so far, across pages. */
  results: AvailabilityResult[]
  error: ApiError | null
  loadingMore: boolean
  loadMoreError: ApiError | null
}

const INITIAL_STATE: AvailabilityState = {
  status: 'idle',
  query: null,
  resultsQuery: null,
  page: null,
  results: [],
  error: null,
  loadingMore: false,
  loadMoreError: null,
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError('server', 'The search failed unexpectedly.', null)
}

/** The search that repeats `page`'s moment exactly: the date and time the
 * API reported, rather than "now" again. */
export function pinnedSearch(
  when: SearchWhen,
  page: AvailabilityPage,
): SearchWhen {
  return page.date ? { kind: 'at', at: `${page.date}T${page.time}` } : when
}

// Appends a page, skipping any room already listed, so a room can't appear
// twice even if the data changed between requests.
function appendNew(
  shown: AvailabilityResult[],
  next: AvailabilityResult[],
): AvailabilityResult[] {
  const ids = new Set(shown.map((result) => result.room_id))
  return [...shown, ...next.filter((result) => !ids.has(result.room_id))]
}

/** Searches a term's availability. A new search aborts any request in flight,
 * so the latest search always wins. */
export function useAvailability(termId: number) {
  const [state, setState] = useState(INITIAL_STATE)
  const controllerRef = useRef<AbortController | null>(null)

  // Aborts the current request and returns a signal for the next one.
  const restart = useCallback(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    return controller.signal
  }, [])

  useEffect(() => () => controllerRef.current?.abort(), [])

  const search = useCallback(
    async (query: SearchQuery) => {
      const signal = restart()
      // Earlier results stay until the new ones arrive, so the layout doesn't
      // jump while loading.
      setState((previous) => ({
        ...previous,
        status: 'loading',
        query,
        error: null,
        loadingMore: false,
        loadMoreError: null,
      }))
      try {
        const page = await fetchAvailability({ termId, ...query, signal })
        if (signal.aborted) return
        setState({
          ...INITIAL_STATE,
          status: 'success',
          query,
          resultsQuery: query,
          page,
          results: page.results,
        })
      } catch (error) {
        if (signal.aborted || isAbort(error)) return
        // Results from an earlier search would be misleading next to an error.
        setState({
          ...INITIAL_STATE,
          status: 'error',
          query,
          error: toApiError(error),
        })
      }
    },
    [termId, restart],
  )

  const loadMore = useCallback(async () => {
    if (
      state.status !== 'success' ||
      !state.resultsQuery ||
      !state.page ||
      state.results.length >= state.page.total
    ) {
      return
    }
    // "now" is worked out from the API's clock on every request, so asking
    // for it again could page through a different minute's rooms. Later pages
    // ask for the exact moment the first page was computed for.
    const { minimumMinutes } = state.resultsQuery
    const when = pinnedSearch(state.resultsQuery.when, state.page)
    const offset = state.results.length
    const signal = restart()
    setState((previous) => ({
      ...previous,
      loadingMore: true,
      loadMoreError: null,
    }))
    try {
      const page = await fetchAvailability({
        termId,
        when,
        minimumMinutes,
        offset,
        signal,
      })
      if (signal.aborted) return
      setState((previous) => ({
        ...previous,
        page,
        results: appendNew(previous.results, page.results),
        loadingMore: false,
      }))
    } catch (error) {
      if (signal.aborted || isAbort(error)) return
      // The rooms already shown are still right, so keep them.
      setState((previous) => ({
        ...previous,
        loadingMore: false,
        loadMoreError: toApiError(error),
      }))
    }
  }, [state, termId, restart])

  const retry = useCallback(() => {
    if (state.query) void search(state.query)
  }, [state.query, search])

  return { ...state, search, loadMore, retry }
}
