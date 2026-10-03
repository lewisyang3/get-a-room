import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  fetchAvailability,
  type AvailabilityPage,
  type AvailabilityResult,
  type SearchWhen,
} from '../api/availability'

export type AvailabilityState = {
  status: 'idle' | 'loading' | 'success' | 'error'
  /** The search being shown or loaded. */
  when: SearchWhen | null
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
  when: null,
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
    async (when: SearchWhen) => {
      const signal = restart()
      // Earlier results stay until the new ones arrive, so the layout doesn't
      // jump while loading.
      setState((previous) => ({
        ...previous,
        status: 'loading',
        when,
        error: null,
        loadingMore: false,
        loadMoreError: null,
      }))
      try {
        const page = await fetchAvailability({ termId, when, signal })
        if (signal.aborted) return
        setState({
          ...INITIAL_STATE,
          status: 'success',
          when,
          page,
          results: page.results,
        })
      } catch (error) {
        if (signal.aborted || isAbort(error)) return
        // Results from an earlier search would be misleading next to an error.
        setState({
          ...INITIAL_STATE,
          status: 'error',
          when,
          error: toApiError(error),
        })
      }
    },
    [termId, restart],
  )

  const loadMore = useCallback(async () => {
    if (
      state.status !== 'success' ||
      !state.when ||
      !state.page ||
      state.results.length >= state.page.total
    ) {
      return
    }
    const { when } = state
    const offset = state.results.length
    const signal = restart()
    setState((previous) => ({
      ...previous,
      loadingMore: true,
      loadMoreError: null,
    }))
    try {
      const page = await fetchAvailability({ termId, when, offset, signal })
      if (signal.aborted) return
      setState((previous) => ({
        ...previous,
        page,
        results: [...previous.results, ...page.results],
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
    if (state.when) void search(state.when)
  }, [state.when, search])

  return { ...state, search, loadMore, retry }
}
