import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Building } from '../api/buildings'
import { expectNoAxeViolations } from '../test/axe'
import { mapbox } from '../test/mapbox'
import CampusMap from './CampusMap'
import type { FreeRoomCounts } from './useBuildingAvailability'

vi.mock('mapbox-gl', async () => (await import('../test/mapbox')).module)

const DWINELLE: Building = {
  building_id: 1,
  building_code: 'DWINELLE',
  building_name: 'Dwinelle',
  latitude: 37.8707,
  longitude: -122.2607,
}
const EVANS: Building = {
  building_id: 2,
  building_code: 'EVANS',
  building_name: 'Evans',
  latitude: 37.8736,
  longitude: -122.2577,
}
const NOWHERE: Building = {
  building_id: 3,
  building_code: 'HFA',
  building_name: 'Hearst Field Annex',
  latitude: null,
  longitude: null,
}

function renderMap({
  counts = new Map([[1, 6]]) as FreeRoomCounts,
  selectedBuildingId = null as number | null,
  onSelect = vi.fn(),
  onUnavailable = vi.fn(),
} = {}) {
  const props = {
    token: 'pk.test',
    buildings: [DWINELLE, EVANS, NOWHERE],
    counts,
    selectedBuildingId,
    onSelect,
    onUnavailable,
  }
  const view = render(<CampusMap {...props} />)
  return {
    ...view,
    onSelect,
    onUnavailable,
    update: (change: Partial<typeof props>) =>
      view.rerender(<CampusMap {...props} {...change} />),
  }
}

afterEach(() => {
  mapbox.reset()
})

describe('CampusMap', () => {
  it('frames every building with a location, using the token', () => {
    renderMap()

    const { options } = mapbox.map
    expect(options.accessToken).toBe('pk.test')
    expect(options.bounds?.points).toContainEqual([-122.2607, 37.8707])
    expect(options.bounds?.points).toContainEqual([-122.2577, 37.8736])
    expect(options.config?.basemap?.lightPreset).toBe('dusk')
    // Tilted, so buildings show in 3D.
    expect(options.fitBoundsOptions).toMatchObject({ pitch: 60 })
  })

  it('shows each located building with how many rooms it has free', () => {
    renderMap()

    expect(
      screen.getByRole('button', { name: 'Dwinelle: 6 rooms free' }),
    ).toHaveTextContent('6')
    // Left out of the counts, so it has none free.
    expect(
      screen.getByRole('button', { name: 'Evans: 0 rooms free' }),
    ).toHaveTextContent('0')
    expect(
      screen.queryByRole('button', { name: /Hearst/ }),
    ).not.toBeInTheDocument()
  })

  it('says one room, not one rooms', () => {
    renderMap({ counts: new Map([[1, 1]]) })

    expect(
      screen.getByRole('button', { name: 'Dwinelle: 1 room free' }),
    ).toBeInTheDocument()
  })

  it("names buildings without a count when counts aren't known", () => {
    renderMap({ counts: 'unknown' })

    expect(screen.getByRole('button', { name: 'Dwinelle' })).toHaveTextContent(
      '',
    )
  })

  it('updates the counts in place', () => {
    const { update } = renderMap()

    update({ counts: new Map([[2, 3]]) })

    expect(
      screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
    ).toBeInTheDocument()
    expect(mapbox.maps).toHaveLength(1)
  })

  it('selects a building, and selecting it again goes back to all', async () => {
    const user = userEvent.setup()
    const { onSelect, update } = renderMap()

    await user.click(screen.getByRole('button', { name: /^Dwinelle/ }))
    expect(onSelect).toHaveBeenLastCalledWith(1)

    update({ selectedBuildingId: 1 })
    await user.click(screen.getByRole('button', { name: /^Dwinelle/ }))
    expect(onSelect).toHaveBeenLastCalledWith(null)
  })

  it('marks the selected building as pressed', () => {
    renderMap({ selectedBuildingId: 2 })

    expect(screen.getByRole('button', { name: /^Evans/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByRole('button', { name: /^Dwinelle/ })).toHaveAttribute(
      'aria-pressed',
      'false',
    )
  })

  it('brings a building selected elsewhere into view', () => {
    const { update } = renderMap()

    update({ selectedBuildingId: 2 })

    expect(mapbox.map.easeTo).toHaveBeenCalledWith({
      center: [-122.2577, 37.8736],
    })
  })

  it('is a labelled region with accessible markers', async () => {
    const { container } = renderMap({ selectedBuildingId: 1 })

    expect(
      screen.getByRole('region', { name: 'Campus map' }),
    ).toBeInTheDocument()
    await expectNoAxeViolations(container)
  })

  it('removes the map when it goes away', () => {
    const { unmount } = renderMap()

    unmount()

    expect(mapbox.map.removed).toBe(true)
  })

  it("reports it's unavailable without WebGL support", () => {
    mapbox.supported = false
    const { onUnavailable } = renderMap()

    expect(onUnavailable).toHaveBeenCalled()
    expect(mapbox.maps).toHaveLength(0)
  })

  it("reports it's unavailable when the map fails to start", () => {
    mapbox.failToCreate = true
    const { onUnavailable } = renderMap()

    expect(onUnavailable).toHaveBeenCalled()
  })

  it("reports it's unavailable when Mapbox rejects the token", () => {
    const { onUnavailable } = renderMap()

    mapbox.map.emit('error', {
      error: { status: 401 },
      sourceId: 'composite',
      tile: {},
    })

    expect(onUnavailable).toHaveBeenCalled()
  })

  it("reports it's unavailable when the style fails to load", () => {
    const { onUnavailable } = renderMap()

    mapbox.map.emit('error', { error: new Error('Failed to fetch') })

    expect(onUnavailable).toHaveBeenCalled()
  })

  it('keeps the map when a tile fails before it loads', () => {
    const { onUnavailable } = renderMap()

    mapbox.map.emit('error', {
      error: { status: 500 },
      sourceId: 'composite',
      tile: {},
    })

    expect(onUnavailable).not.toHaveBeenCalled()
  })

  it('keeps the map when something else fails after the style loads', () => {
    const { onUnavailable } = renderMap()

    mapbox.map.emit('style.load')
    mapbox.map.emit('error', { error: new Error('Failed to load sprite') })

    expect(onUnavailable).not.toHaveBeenCalled()
  })

  it('keeps the map after an error once it has loaded', () => {
    const { onUnavailable } = renderMap()

    mapbox.map.emit('load')
    mapbox.map.emit('error', { error: new Error('Tile not found') })

    expect(onUnavailable).not.toHaveBeenCalled()
  })
})
