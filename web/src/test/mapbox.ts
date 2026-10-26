import { vi } from 'vitest'

/** A stand-in for mapbox-gl, which needs WebGL and so can't run in jsdom.
 * Use it with:
 *
 *     vi.mock('mapbox-gl', async () => (await import('../test/mapbox')).module)
 *
 * Markers are added to the map's container, so tests can find and click
 * them like any other element.
 *
 * The map's style loads at once, and its GeoJSON sources don't cluster:
 * `querySourceFeatures` returns every point in the source, unless a test
 * sets `map.onScreen` to what's on screen, e.g. a group built with
 * `clusterFeature`, and emits 'render'. */

type LngLat = [number, number]

type Feature = {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: LngLat }
  properties: Record<string, unknown>
}

export const mapbox = {
  /** Whether the browser "supports" Mapbox GL. */
  supported: true,
  /** Whether creating a map throws, as it does when WebGL fails. */
  failToCreate: false,
  /** Whether the map's style has loaded when the map is created. */
  styleLoaded: true,
  /** The zoom at which a group splits. */
  expansionZoom: 17,
  /** Every map created, newest last. */
  maps: [] as FakeMap[],
  reset() {
    this.supported = true
    this.failToCreate = false
    this.styleLoaded = true
    this.expansionZoom = 17
    this.maps = []
  },
  /** The latest map. */
  get map(): FakeMap {
    const map = this.maps.at(-1)
    if (!map) throw new Error('No map was created')
    return map
  },
}

type MapOptions = {
  container: HTMLElement
  config?: { basemap?: { lightPreset?: string } }
  [key: string]: unknown
}

class FakeMap {
  readonly options: MapOptions
  readonly easeTo = vi.fn()
  readonly setConfigProperty = vi.fn()
  readonly addLayer = vi.fn()
  readonly addSource = vi.fn((id: string, spec: SourceSpec) => {
    this.sources.set(id, new FakeGeoJSONSource(this, spec))
    return this
  })
  readonly isSourceLoaded = vi.fn((_id: string) => true)
  readonly isMoving = vi.fn(() => false)
  /** What's on screen, if not every point in the source. */
  onScreen: Feature[] | null = null
  removed = false
  private readonly sources = new Map<string, FakeGeoJSONSource>()
  private readonly listeners = new Map<string, ((event?: unknown) => void)[]>()

  constructor(options: MapOptions) {
    if (mapbox.failToCreate) throw new Error('Failed to initialize WebGL')
    this.options = options
    mapbox.maps.push(this)
  }

  on(type: string, listener: (event?: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener])
    return this
  }

  once(type: string, listener: (event?: unknown) => void) {
    const wrapped = (event?: unknown) => {
      this.listeners.set(
        type,
        (this.listeners.get(type) ?? []).filter((l) => l !== wrapped),
      )
      listener(event)
    }
    return this.on(type, wrapped)
  }

  /** Fires an event, as Mapbox does, e.g. 'load' or 'error'. */
  emit(type: string, event?: unknown) {
    for (const listener of this.listeners.get(type) ?? []) listener(event)
  }

  isStyleLoaded() {
    return mapbox.styleLoaded
  }

  getSource(id: string): FakeGeoJSONSource | undefined {
    return this.sources.get(id)
  }

  querySourceFeatures(id: string): Feature[] {
    return this.onScreen ?? this.sources.get(id)?.data.features ?? []
  }

  remove() {
    this.removed = true
  }
}

type SourceSpec = { data: { features: Feature[] }; [key: string]: unknown }

class FakeGeoJSONSource {
  readonly spec: SourceSpec
  data: { features: Feature[] }
  private readonly map: FakeMap

  constructor(map: FakeMap, spec: SourceSpec) {
    this.map = map
    this.spec = spec
    this.data = spec.data
  }

  /** Replaces the points, then renders, as Mapbox does once they load. */
  readonly setData = vi.fn((data: { features: Feature[] }) => {
    this.data = data
    this.map.emit('render')
    return this
  })

  readonly getClusterExpansionZoom = vi.fn(
    (_id: number, callback: (error: Error | null, zoom: number) => void) => {
      callback(null, mapbox.expansionZoom)
      return this
    },
  )
}

/** A building on its own, as `querySourceFeatures` returns it. */
export function pointFeature(
  building: { building_id: number; latitude: number; longitude: number },
  free = 0,
): Feature {
  return {
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [building.longitude, building.latitude],
    },
    properties: { building_id: building.building_id, free },
  }
}

/** A group of buildings, as `querySourceFeatures` returns it. */
export function clusterFeature({
  id,
  lngLat = [-122.26, 37.872],
  buildings,
  free,
}: {
  id: number
  lngLat?: LngLat
  buildings: number
  free: number
}): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: lngLat },
    properties: {
      cluster: true,
      cluster_id: id,
      point_count: buildings,
      free,
    },
  }
}

class FakeMarker {
  readonly element: HTMLElement
  lngLat: LngLat | null = null

  constructor({ element }: { element: HTMLElement }) {
    this.element = element
  }

  getElement() {
    return this.element
  }

  setLngLat(lngLat: LngLat) {
    this.lngLat = lngLat
    return this
  }

  addTo(map: FakeMap) {
    map.options.container.append(this.element)
    return this
  }

  remove() {
    this.element.remove()
    return this
  }
}

export const module = {
  default: {
    Map: FakeMap,
    Marker: FakeMarker,
    supported: () => mapbox.supported,
  },
}
