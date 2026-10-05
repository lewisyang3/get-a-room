import { useEffect, useState } from 'react'
import { fetchBuildings, type Building } from '../api/buildings'

/** Loads the buildings to filter by, once. Returns null while loading, and
 * after a failure or for an empty list: the building filter is optional, so
 * without a list the page just searches every building. */
export function useBuildings(): Building[] | null {
  const [buildings, setBuildings] = useState<Building[] | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchBuildings({ signal: controller.signal }).then(
      (list) => {
        if (!controller.signal.aborted && list.length > 0) setBuildings(list)
      },
      () => {},
    )
    return () => controller.abort()
  }, [])

  return buildings
}
