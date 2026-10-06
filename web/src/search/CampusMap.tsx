import { useEffect, useEffectEvent, useMemo, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Building } from '../api/buildings'
import type { FreeRoomCounts } from './useBuildingAvailability'
import styles from './CampusMap.module.css'

type Props = {
  token: string
  /** Every building; those without coordinates get no marker. */
  buildings: Building[]
  counts: FreeRoomCounts
  selectedBuildingId: number | null
  /** Called with a building's id, or null to go back to every building. */
  onSelect: (buildingId: number | null) => void
  /** Called when the map can't be shown, e.g. without WebGL, or when Mapbox
   * can't load it, e.g. because it rejects the token. */
  onUnavailable: () => void
}

type LocatedBuilding = Building & { latitude: number; longitude: number }

const DARK_SCHEME = '(prefers-color-scheme: dark)'

// The Standard style's lighting, following the page's light or dark theme.
// Dusk rather than night in dark mode: night lights buildings so dimly that
// their 3D shapes barely show.
function lightPreset(): 'day' | 'dusk' {
  return window.matchMedia?.(DARK_SCHEME).matches ? 'dusk' : 'day'
}

function isLocated(building: Building): building is LocatedBuilding {
  return building.latitude !== null && building.longitude !== null
}

function lngLat(building: LocatedBuilding): [number, number] {
  return [building.longitude, building.latitude]
}

/** What a marker shows: its count, and a name that says what the count is. */
function markerContent(building: Building, counts: FreeRoomCounts) {
  const name = building.building_name
  if (counts === 'unknown') return { text: '', label: name, kind: 'unknown' }
  const free = counts.get(building.building_id) ?? 0
  const rooms = free === 1 ? 'room' : 'rooms'
  return {
    text: String(free),
    label: `${name}: ${free} ${rooms} free`,
    kind: free > 0 ? 'free' : 'none',
  } as const
}

/** A Mapbox map of campus with one button per building, showing how many
 * rooms it has free. Choosing a building's button selects it; choosing it
 * again goes back to every building. */
function CampusMap({
  token,
  buildings,
  counts,
  selectedBuildingId,
  onSelect,
  onUnavailable,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map | null>(null)
  const located = useMemo(() => buildings.filter(isLocated), [buildings])

  // Each building's marker is a button. Mapbox gives a marker element
  // role="img" unless it has a role, which would hide a button inside it
  // from screen readers, so the element is the button itself.
  const markers = useMemo(
    () =>
      new Map(
        located.map((building) => {
          const button = document.createElement('button')
          button.type = 'button'
          button.setAttribute('role', 'button')
          button.setAttribute('aria-label', building.building_name)
          button.classList.add(styles.marker)
          return [building.building_id, button] as const
        }),
      ),
    [located],
  )

  const select = useEffectEvent((buildingId: number) => {
    onSelect(buildingId === selectedBuildingId ? null : buildingId)
  })
  const unavailable = useEffectEvent(() => onUnavailable())

  // Creates the map, framing every building. The token and buildings are
  // set once per visit, so in practice this runs once; markers, counts, and
  // selection update the map in place.
  useEffect(() => {
    const container = containerRef.current
    if (!container || located.length === 0) return
    if (!mapboxgl.supported()) {
      unavailable()
      return
    }
    const bounds = new mapboxgl.LngLatBounds()
    for (const building of located) bounds.extend(lngLat(building))
    let map: mapboxgl.Map
    try {
      map = new mapboxgl.Map({
        container,
        accessToken: token,
        style: 'mapbox://styles/mapbox/standard',
        config: { basemap: { lightPreset: lightPreset() } },
        bounds,
        // Tilted and turned, so the Standard style's 3D buildings and trees
        // show their height. The fit sets the camera, so the tilt goes here.
        fitBoundsOptions: { padding: 40, maxZoom: 17, pitch: 60, bearing: -20 },
      })
    } catch {
      unavailable()
      return
    }
    mapRef.current = map

    // An error before the map first loads, e.g. Mapbox rejecting the token or
    // the style, leaves it blank. Errors after that, e.g. a missing tile,
    // leave a working map, so they're ignored.
    let loaded = false
    map.once('load', () => {
      loaded = true
    })
    map.on('error', () => {
      if (!loaded) unavailable()
    })

    // Places a marker for each building with a location.
    const placed = located.map((building) => {
      const element = markers.get(building.building_id)!
      element.onclick = () => select(building.building_id)
      return new mapboxgl.Marker({ element, anchor: 'center' })
        .setLngLat(lngLat(building))
        .addTo(map)
    })

    // Follows the page's theme when it changes.
    const scheme = window.matchMedia?.(DARK_SCHEME)
    const followScheme = () =>
      map.setConfigProperty('basemap', 'lightPreset', lightPreset())
    scheme?.addEventListener('change', followScheme)

    return () => {
      scheme?.removeEventListener('change', followScheme)
      placed.forEach((marker) => marker.remove())
      mapRef.current = null
      map.remove()
    }
  }, [token, located, markers])

  // Shows each building's count, and which one is selected.
  useEffect(() => {
    for (const building of located) {
      const element = markers.get(building.building_id)!
      const { text, label, kind } = markerContent(building, counts)
      const selected = building.building_id === selectedBuildingId
      element.textContent = text
      element.setAttribute('aria-label', label)
      element.setAttribute('aria-pressed', String(selected))
      // Toggles only this component's classes; Mapbox adds its own.
      for (const state of ['free', 'none', 'unknown'] as const) {
        element.classList.toggle(styles[state], state === kind)
      }
      element.classList.toggle(styles.selected, selected)
    }
  }, [located, markers, counts, selectedBuildingId])

  // Brings a building chosen elsewhere, e.g. the Building filter, into view.
  // Not marked essential, so Mapbox skips the movement for people who prefer
  // reduced motion.
  useEffect(() => {
    const building = located.find((b) => b.building_id === selectedBuildingId)
    if (building) mapRef.current?.easeTo({ center: lngLat(building) })
  }, [located, selectedBuildingId])

  return (
    <div
      ref={containerRef}
      className={styles.map}
      role="region"
      aria-label="Campus map"
    />
  )
}

export default CampusMap
