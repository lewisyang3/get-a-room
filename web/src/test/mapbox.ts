import { vi } from 'vitest'

/** A stand-in for mapbox-gl, which needs WebGL and so can't run in jsdom.
 * Use it with:
 *
 *     vi.mock('mapbox-gl', async () => (await import('../test/mapbox')).module)
 *
 * Markers are added to the map's container, so tests can find and click
 * them like any other element. */

type LngLat = [number, number]

export const mapbox = {
  /** Whether the browser "supports" Mapbox GL. */
  supported: true,
  /** Whether creating a map throws, as it does when WebGL fails. */
  failToCreate: false,
  /** Every map created, newest last. */
  maps: [] as FakeMap[],
  reset() {
    this.supported = true
    this.failToCreate = false
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
  bounds?: FakeLngLatBounds
  [key: string]: unknown
}

class FakeMap {
  readonly options: MapOptions
  readonly easeTo = vi.fn()
  readonly setConfigProperty = vi.fn()
  removed = false

  constructor(options: MapOptions) {
    if (mapbox.failToCreate) throw new Error('Failed to initialize WebGL')
    this.options = options
    mapbox.maps.push(this)
  }

  remove() {
    this.removed = true
  }
}

class FakeMarker {
  readonly element: HTMLElement
  lngLat: LngLat | null = null

  constructor({ element }: { element: HTMLElement }) {
    this.element = element
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

class FakeLngLatBounds {
  readonly points: LngLat[] = []

  extend(point: LngLat) {
    this.points.push(point)
    return this
  }
}

export const module = {
  default: {
    Map: FakeMap,
    Marker: FakeMarker,
    LngLatBounds: FakeLngLatBounds,
    supported: () => mapbox.supported,
  },
}
