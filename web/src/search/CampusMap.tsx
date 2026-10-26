import { useEffect, useEffectEvent, useMemo, useRef } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Building } from '../api/buildings'
import {
  buildingFeatures,
  CLUSTER_PROPERTIES,
  clusterContent,
  isLocated,
  lngLat,
  markerContent,
  markersOnScreen,
  type OnScreen,
  type SourceFeature,
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

// The GeoJSON source Mapbox groups nearby buildings in.
const SOURCE_ID = 'buildings'

// How close buildings group, in pixels: a little more than a pill's width,
// so pills that would overlap merge instead.
const CLUSTER_RADIUS = 40

// The last zoom at which buildings group. Mapbox's default, 14, is below the
// starting view; from 17 every building is shown on its own.
const CLUSTER_MAX_ZOOM = 16

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
 * component's classes; Mapbox adds its own. */
function showContent(
  element: HTMLElement,
  { text, label, kind }: { text: string; label: string; kind: string },
) {
  element.firstElementChild!.textContent = text
  element.setAttribute('aria-label', label)
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
  const sourceRef = useRef<mapboxgl.GeoJSONSource | null>(null)
  // What Mapbox last showed: buildings on their own, and groups.
  const onScreenRef = useRef<OnScreen>(markersOnScreen([]))
  // Each group's marker, by Mapbox's cluster id.
  const clustersRef = useRef(
    new Map<number, { marker: mapboxgl.Marker; element: HTMLElement }>(),
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

  // Zooms in far enough for a group to split.
  const zoomInto = useEffectEvent((clusterId: number) => {
    const cluster = onScreenRef.current.clusters.get(clusterId)
    if (!cluster) return
    sourceRef.current?.getClusterExpansionZoom(clusterId, (error, zoom) => {
      if (error || zoom == null) return
      // Not marked essential, so Mapbox skips the movement for people who
      // prefer reduced motion.
      mapRef.current?.easeTo({ center: cluster.lngLat, zoom })
    })
  })

  // Shows what Mapbox last showed. A building is shown on its own, or if
  // it's selected, or if it has focus, e.g. just deselected with the
  // keyboard, until focus leaves. A group's marker is made when it appears
  // and removed when it goes, except a focused one while the map moves; once
  // it stops, focus goes to the map.
  const render = useEffectEvent(() => {
    const map = mapRef.current
    if (!map) return
    const { buildingIds, clusters } = onScreenRef.current
    for (const building of located) {
      const id = building.building_id
      const element = markers.get(id)!
      element.hidden = !(
        buildingIds.has(id) ||
        id === selectedBuildingId ||
        element.contains(document.activeElement)
      )
    }

    const shown = clustersRef.current
    for (const [id, cluster] of clusters) {
      let entry = shown.get(id)
      if (!entry) {
        const element = markerButton('')
        element.classList.add(styles.cluster)
        element.addEventListener('click', () => zoomInto(id))
        const marker = new mapboxgl.Marker({ element, anchor: 'center' })
        entry = { marker, element }
        shown.set(id, entry)
        marker.setLngLat(cluster.lngLat).addTo(map)
      }
      entry.marker.setLngLat(cluster.lngLat)
      showContent(entry.element, clusterContent(cluster, counts))
    }
    for (const [id, { marker, element }] of shown) {
      if (clusters.has(id)) continue
      const focused = element.contains(document.activeElement)
      if (focused && map.isMoving()) continue
      marker.remove()
      shown.delete(id)
      if (focused) containerRef.current?.focus()
    }
  })

  // Reads what Mapbox shows, once the source has loaded. While it reloads,
  // e.g. after new counts or a zoom, the last markers stay, so they don't
  // flicker.
  const refresh = useEffectEvent(() => {
    const map = mapRef.current
    if (!map || !sourceRef.current || !map.isSourceLoaded(SOURCE_ID)) return
    // GeoJSON's types aren't installed, so Mapbox's features lack theirs.
    const features = map.querySourceFeatures(
      SOURCE_ID,
    ) as unknown as SourceFeature[]
    onScreenRef.current = markersOnScreen(features)
    render()
  })

  // Adds the buildings for Mapbox to group, with a layer that draws nothing
  // but makes Mapbox load them; a hidden layer wouldn't.
  const addSource = useEffectEvent((map: mapboxgl.Map) => {
    map.addSource(SOURCE_ID, {
      type: 'geojson',
      data: buildingFeatures(located, counts, selectedBuildingId),
      cluster: true,
      clusterRadius: CLUSTER_RADIUS,
      clusterMaxZoom: CLUSTER_MAX_ZOOM,
      clusterProperties: CLUSTER_PROPERTIES,
    })
    map.addLayer({
      id: SOURCE_ID,
      type: 'circle',
      source: SOURCE_ID,
      paint: { 'circle-radius': 0, 'circle-opacity': 0 },
    })
    sourceRef.current = map.getSource<mapboxgl.GeoJSONSource>(SOURCE_ID) ?? null
    refresh()
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

    // Sources can only be added once the style has loaded.
    if (map.isStyleLoaded()) addSource(map)
    else map.once('style.load', () => addSource(map))
    map.on('render', () => refresh())
    map.on('moveend', () => refresh())

    // Places a marker for each building with a location. One kept only
    // because it had focus goes once focus leaves.
    const onFocusOut = (event: FocusEvent) => {
      // The window lost focus, and it comes back here, so keep it.
      if (document.activeElement === event.currentTarget) return
      render()
    }
    const placed = located.map((building) => {
      const element = markers.get(building.building_id)!
      element.onclick = () => select(building.building_id)
      element.addEventListener('focusout', onFocusOut)
      return new mapboxgl.Marker({ element, anchor: 'center' })
        .setLngLat(lngLat(building))
        .addTo(map)
    })

    const clusters = clustersRef.current
    return () => {
      placed.forEach((marker) => {
        marker.getElement().removeEventListener('focusout', onFocusOut)
        marker.remove()
      })
      clusters.forEach(({ marker }) => marker.remove())
      clusters.clear()
      onScreenRef.current = markersOnScreen([])
      sourceRef.current = null
      mapRef.current = null
      map.remove()
    }
  }, [token, located, markers])

  // Shows each building's count, and which one is selected, and gives
  // Mapbox the buildings to group.
  useEffect(() => {
    for (const building of located) {
      const element = markers.get(building.building_id)!
      const selected = building.building_id === selectedBuildingId
      showContent(element, markerContent(building, counts))
      element.setAttribute('aria-pressed', String(selected))
      element.classList.toggle(styles.selected, selected)
    }
    sourceRef.current?.setData(
      buildingFeatures(located, counts, selectedBuildingId),
    )
    render()
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
