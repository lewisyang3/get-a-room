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
  [key: string]: unknown
}

class FakeMap {
  readonly options: MapOptions
  readonly easeTo = vi.fn()
  readonly setConfigProperty = vi.fn()
  removed = false
  private readonly listeners = new Map<string, ((event?: unknown) => void)[]>()
  private readonly canvas = document.createElement('canvas')

  constructor(options: MapOptions) {
    if (mapbox.failToCreate) throw new Error('Failed to initialize WebGL')
    this.options = options
    // Focusable, as Mapbox's canvas is.
    this.canvas.tabIndex = 0
    options.container.append(this.canvas)
    mapbox.maps.push(this)
  }

  getCanvas() {
    return this.canvas
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

export const module = {
  default: {
    Map: FakeMap,
    Marker: FakeMarker,
    supported: () => mapbox.supported,
  },
}
