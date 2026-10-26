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

// The Standard style's lighting, matching the page's dark theme. Dusk rather
// than night: night lights buildings so dimly that their 3D shapes barely show.
const LIGHT_PRESET = 'dusk'

// Where the map starts: central campus, from Doe Library, close enough that
// the Standard style's 3D buildings show. Tilted and turned, so buildings and
// trees show their height. A fixed view rather than a fit around every
// building, which leaves campus too small to see them.
const START_VIEW = {
  center: [-122.2594, 37.8722] as [number, number],
  zoom: 15.55,
  pitch: 60,
  bearing: -20,
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

/** The parts of a Mapbox error event that say what failed. A request that
 * failed has the response's status, and an error about a source or one of
 * its tiles names the source. */
type MapError = {
  error?: Error & { status?: unknown }
  sourceId?: string
  tile?: unknown
}

/** Whether an error before the map loads means it never will: Mapbox
 * rejecting the token, which fails every request, or the style failing
 * before it loads. A failed tile or source, e.g. on a patchy network, just
 * leaves a gap, so the map is kept. */
function stopsTheMap(event: MapError, styleLoaded: boolean): boolean {
  const status = event.error?.status
  if (status === 401 || status === 403) return true
  if (event.sourceId !== undefined || event.tile !== undefined) return false
  return !styleLoaded
}

/** A Mapbox map of campus with one button per building, showing how many
 * rooms it has free. Buildings with none free are left off, unless
 * selected. Choosing a building's button selects it; choosing it again goes
 * back to every building. */
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
  // from screen readers, so the element is the button itself. The pill is a
  // span inside it, so it can scale in place: Mapbox positions the button
  // with `transform`, and scaling the button would scale that offset too,
  // sliding the marker off its building.
  const markers = useMemo(
    () =>
      new Map(
        located.map((building) => {
          const button = document.createElement('button')
          button.type = 'button'
          button.setAttribute('role', 'button')
          button.setAttribute('aria-label', building.building_name)
          button.classList.add(styles.marker)
          const pill = document.createElement('span')
          pill.classList.add(styles.pill)
          button.append(pill)
          // A marker kept only because it had focus goes once focus leaves.
          button.addEventListener('focusout', () => {
            // The window lost focus, and it comes back here, so keep it.
            if (document.activeElement === button) return
            button.hidden = button.dataset.leftOff === 'true'
          })
          return [building.building_id, button] as const
        }),
      ),
    [located],
  )

  const select = useEffectEvent((buildingId: number) => {
    onSelect(buildingId === selectedBuildingId ? null : buildingId)
  })
  const unavailable = useEffectEvent(() => onUnavailable())

  // Creates the map over central campus. The token and buildings are
  // set once per visit, so in practice this runs once; markers, counts, and
  // selection update the map in place.
  useEffect(() => {
    const container = containerRef.current
    if (!container || located.length === 0) return
    if (!mapboxgl.supported()) {
      unavailable()
      return
    }
    let map: mapboxgl.Map
    try {
      map = new mapboxgl.Map({
        container,
        accessToken: token,
        style: 'mapbox://styles/mapbox/standard',
        config: { basemap: { lightPreset: LIGHT_PRESET } },
        ...START_VIEW,
      })
    } catch {
      unavailable()
      return
    }
    mapRef.current = map

    // Some errors before the map first loads leave it blank; see
    // stopsTheMap. Errors after that leave a working map, so they're ignored.
    let styleLoaded = false
    let loaded = false
    map.once('style.load', () => {
      styleLoaded = true
    })
    map.once('load', () => {
      loaded = true
    })
    map.on('error', (event: MapError) => {
      if (!loaded && stopsTheMap(event, styleLoaded)) unavailable()
    })

    // Places a marker for each building with a location.
    const placed = located.map((building) => {
      const element = markers.get(building.building_id)!
      element.onclick = () => select(building.building_id)
      return new mapboxgl.Marker({ element, anchor: 'center' })
        .setLngLat(lngLat(building))
        .addTo(map)
    })

    return () => {
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
      // No room free: left off the map, unless it's selected, or focused, e.g.
      // just deselected with the keyboard. That one goes when focus leaves.
      const leftOff = kind === 'none' && !selected
      element.dataset.leftOff = String(leftOff)
      element.hidden = leftOff && !element.contains(document.activeElement)
      element.firstElementChild!.textContent = text
      element.setAttribute('aria-label', label)
      element.setAttribute('aria-pressed', String(selected))
      // Toggles only this component's classes; Mapbox adds its own.
      for (const state of ['free', 'none', 'unknown'] as const) {
        element.classList.toggle(styles[state], state === kind)
      }
      element.classList.toggle(styles.selected, selected)
    }
  }, [located, markers, counts, selectedBuildingId])

  // Brings the selected building into view.
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
