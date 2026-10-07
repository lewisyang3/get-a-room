import { useEffect, useEffectEvent, useState } from 'react'
import type { AvailabilityPage } from '../api/availability'
import { fetchBuildingAvailability } from '../api/buildingAvailability'
import { pinnedAt, requestFor, type SearchQuery } from './useAvailability'

/** How many rooms each building has free, by building id, or 'unknown'
 * before the first counts arrive or after they fail. A building that isn't
 * in the map has none free. */
export type FreeRoomCounts = ReadonlyMap<number, number> | 'unknown'

/** Counts each building's free rooms for the search on screen. Counts every
 * building, whichever one is selected, so the map can show them all. Earlier
 * counts stay while new ones load, so markers don't flicker. */
export function useBuildingAvailability(
  termId: number,
  resultsQuery: SearchQuery | null,
  page: AvailabilityPage | null,
): FreeRoomCounts {
  const [counts, setCounts] = useState<FreeRoomCounts>('unknown')

  // Reads the page the query produced, without refetching when Show more
  // replaces it, to ask for the same minute the list shows rather than
  // "now" again.
  const request = useEffectEvent((query: SearchQuery) => ({
    termId,
    at: page ? pinnedAt(page) : null,
    ...requestFor({ ...query, buildingId: null }),
  }))

  useEffect(() => {
    if (resultsQuery === null) return
    const controller = new AbortController()
    const { signal } = controller
    fetchBuildingAvailability({ ...request(resultsQuery), signal }).then(
      (list) => {
        if (signal.aborted) return
        setCounts(
          new Map(list.results.map((b) => [b.building_id, b.free_rooms])),
        )
      },
      () => {
        if (!signal.aborted) setCounts('unknown')
      },
    )
    return () => controller.abort()
  }, [termId, resultsQuery])

  return resultsQuery === null ? 'unknown' : counts
}
