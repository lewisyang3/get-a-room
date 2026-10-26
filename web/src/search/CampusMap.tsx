import { useEffect, useEffectEvent, useMemo, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Building } from '../api/buildings'
import {
  buildingPoints,
  type Cluster,
  clusterContent,
  clusterIndex,
  type ClusterIndex,
  groupsOnScreen,
  isLocated,
  lngLat,
  markerContent,
} from './campusMapFeatures'
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

/** A marker's button, with a pill inside. Mapbox gives a marker element
 * role="img" unless it has a role, which would hide a button inside it
 * from screen readers, so the element is the button itself. The pill is a
 * span inside it, so it can scale in place: Mapbox positions the button
 * with `transform`, and scaling the button would scale that offset too,
 * sliding the marker off its building. */
function markerButton(label: string): HTMLButtonElement {
  const button = document.createElement('button')
  button.type = 'button'
  button.setAttribute('role', 'button')
  button.setAttribute('aria-label', label)
  button.classList.add(styles.marker)
  const pill = document.createElement('span')
  pill.classList.add(styles.pill)
  button.append(pill)
  return button
}

/** Shows a marker's text, and toggles its kind's class. Toggles only this
 * component's classes; Mapbox adds its own. Text that hasn't changed isn't
 * rewritten, so screen readers don't announce it again. */
function showContent(
  element: HTMLElement,
  { text, label, kind }: { text: string; label: string; kind: string },
) {
  const pill = element.firstElementChild!
  if (pill.textContent !== text) pill.textContent = text
  if (element.getAttribute('aria-label') !== label) {
    element.setAttribute('aria-label', label)
  }
  for (const state of ['free', 'none', 'unknown'] as const) {
    element.classList.toggle(styles[state], state === kind)
  }
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
 * selected. Nearby buildings group into one button showing their total,
 * which zooms in when chosen. Choosing a building's button selects it;
 * choosing it again goes back to every building. */
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
  // The buildings grouped at every zoom, made again when they change.
  const indexRef = useRef<ClusterIndex | null>(null)
  // The building whose marker has focus, which is never grouped.
  const focusedRef = useRef<number | null>(null)
  // Each group's marker, by its id, with the group it last showed.
  const clustersRef = useRef(
    new Map<
      number,
      { marker: mapboxgl.Marker; element: HTMLElement; cluster: Cluster }
    >(),
  )
  const located = useMemo(() => buildings.filter(isLocated), [buildings])

  // Each building's marker, made once and kept on the map; buildings that
  // aren't shown are hidden.
  const markers = useMemo(
    () =>
      new Map(
        located.map((building) => [
          building.building_id,
          markerButton(building.building_name),
        ]),
      ),
    [located],
  )

  const select = useEffectEvent((buildingId: number) => {
    onSelect(buildingId === selectedBuildingId ? null : buildingId)
  })
  const unavailable = useEffectEvent(() => onUnavailable())

  // Shows the buildings and groups in view. A building is shown on its own,
  // or if it's selected, or if it has focus, e.g. just deselected with the
  // keyboard, until focus leaves. Runs when the map stops moving, not as it
  // moves: Mapbox keeps each marker in place meanwhile.
  const update = useEffectEvent(() => {
    const map = mapRef.current
    const index = indexRef.current
    const bounds = map?.getBounds()
    if (!map || !index || !bounds) return
    const { buildingIds, clusters } = groupsOnScreen(
      index,
      [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ],
      map.getZoom(),
    )

    for (const building of located) {
      const id = building.building_id
      const element = markers.get(id)!
      const hidden = !(
        buildingIds.has(id) ||
        id === selectedBuildingId ||
        element.contains(document.activeElement)
      )
      if (element.hidden !== hidden) element.hidden = hidden
    }

    // A group's marker is made when it appears and removed when it goes.
    // Choosing it zooms in far enough for it to split, using the group it
    // shows, so it works while the map is still moving.
    const shown = clustersRef.current
    for (const [id, cluster] of clusters) {
      let entry = shown.get(id)
      if (entry) {
        entry.cluster = cluster
        entry.marker.setLngLat(cluster.lngLat)
      } else {
        const element = markerButton('')
        element.classList.add(styles.cluster)
        const marker = new mapboxgl.Marker({ element, anchor: 'center' })
          .setLngLat(cluster.lngLat)
          .addTo(map)
        const added = { marker, element, cluster }
        // Not marked essential, so Mapbox skips the movement for people who
        // prefer reduced motion.
        element.addEventListener('click', () =>
          mapRef.current?.easeTo({
            center: added.cluster.lngLat,
            zoom: added.cluster.expansionZoom,
          }),
        )
        shown.set(id, added)
        entry = added
      }
      showContent(entry.element, clusterContent(cluster, counts))
    }
    // A focused group that goes, e.g. split by zooming in, hands focus to
    // the map, without scrolling the page to it.
    for (const [id, { marker, element }] of shown) {
      if (clusters.has(id)) continue
      const focused = element.contains(document.activeElement)
      marker.remove()
      shown.delete(id)
      if (focused) containerRef.current?.focus({ preventScroll: true })
    }
  })

  // Groups the buildings again, e.g. after new counts, then shows them. The
  // selected and focused buildings are left out, so they're always shown on
  // their own and never counted in a group too.
  const regroup = useEffectEvent(() => {
    const leftOut = new Set<number>()
    if (selectedBuildingId !== null) leftOut.add(selectedBuildingId)
    if (focusedRef.current !== null) leftOut.add(focusedRef.current)
    indexRef.current = clusterIndex(buildingPoints(located, counts, leftOut))
    update()
  })

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
    map.on('moveend', () => update())

    // Places a marker for each building with a location. A focused one
    // stays out of groups until focus leaves.
    const placed = located.map((building) => {
      const id = building.building_id
      const element = markers.get(id)!
      element.onclick = () => select(id)
      element.onfocus = () => {
        focusedRef.current = id
        regroup()
      }
      element.onblur = () => {
        // The window lost focus, and it comes back here, so keep it.
        if (document.activeElement === element) return
        if (focusedRef.current === id) focusedRef.current = null
        regroup()
      }
      return new mapboxgl.Marker({ element, anchor: 'center' })
        .setLngLat(lngLat(building))
        .addTo(map)
    })
    // Shows the buildings straight away, without waiting for the style.
    regroup()

    const clusters = clustersRef.current
    return () => {
      placed.forEach((marker) => marker.remove())
      clusters.forEach(({ marker }) => marker.remove())
      clusters.clear()
      indexRef.current = null
      focusedRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [token, located, markers])

  // Shows each building's count, and which one is selected, and groups the
  // buildings again.
  useEffect(() => {
    for (const building of located) {
      const element = markers.get(building.building_id)!
      const selected = building.building_id === selectedBuildingId
      showContent(element, markerContent(building, counts))
      element.setAttribute('aria-pressed', String(selected))
      element.classList.toggle(styles.selected, selected)
    }
    regroup()
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
      // Takes focus when a focused group goes, without being a Tab stop.
      tabIndex={-1}
    />
  )
}

export default CampusMap
