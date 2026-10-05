import { useCallback, useState } from 'react'
import type { Point } from '../api/availability'

export type LocationStatus = 'idle' | 'locating' | 'ready' | 'failed'

/** Rounds to 3 decimal places, about 100 m: enough to sort buildings by
 * distance, without sending a precise location. */
export function roundPoint({ latitude, longitude }: Point): Point {
  const round = (value: number) => Math.round(value * 1000) / 1000
  return { latitude: round(latitude), longitude: round(longitude) }
}

function isSupported(): boolean {
  return typeof navigator !== 'undefined' && 'geolocation' in navigator
}

/** The device's location, asked for only when `locate` is called, rounded,
 * and kept for the rest of the visit. */
export function useLocation() {
  const [point, setPoint] = useState<Point | null>(null)
  const [status, setStatus] = useState<LocationStatus>('idle')
  const supported = isSupported()

  // Resolves with the location, or null if it can't be found. Asks the
  // device only the first time it succeeds.
  const locate = useCallback(
    () =>
      new Promise<Point | null>((resolve) => {
        if (point !== null) {
          resolve(point)
          return
        }
        if (!isSupported()) {
          setStatus('failed')
          resolve(null)
          return
        }
        setStatus('locating')
        navigator.geolocation.getCurrentPosition(
          (position) => {
            const rounded = roundPoint(position.coords)
            setPoint(rounded)
            setStatus('ready')
            resolve(rounded)
          },
          () => {
            setStatus('failed')
            resolve(null)
          },
          { timeout: 10_000, maximumAge: 5 * 60_000 },
        )
      }),
    [point],
  )

  return { supported, point, status, locate }
}
