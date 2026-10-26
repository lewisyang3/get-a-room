import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Building } from '../api/buildings'
import { expectNoAxeViolations } from '../test/axe'
import { clusterFeature, mapbox, pointFeature } from '../test/mapbox'
import CampusMap from './CampusMap'
import type { LocatedBuilding } from './campusMapFeatures'
import type { FreeRoomCounts } from './useBuildingAvailability'

vi.mock('mapbox-gl', async () => (await import('../test/mapbox')).module)

const DWINELLE: LocatedBuilding = {
  building_id: 1,
  building_code: 'DWINELLE',
  building_name: 'Dwinelle',
  latitude: 37.8707,
  longitude: -122.2607,
}
const EVANS: LocatedBuilding = {
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
  it('starts over central campus, using the token', () => {
    renderMap()

    const { options } = mapbox.map
    expect(options.accessToken).toBe('pk.test')
    expect(options.center).toEqual([-122.2594, 37.8722])
    expect(options.config?.basemap?.lightPreset).toBe('dusk')
    // Tilted, so buildings show in 3D.
    expect(options).toMatchObject({ pitch: 60 })
  })

  it('shows each located building with how many rooms it has free', () => {
    renderMap()

    expect(
      screen.getByRole('button', { name: 'Dwinelle: 6 rooms free' }),
    ).toHaveTextContent('6')
    // Left out of the counts, so it has none free and is left off the map.
    expect(
      screen.queryByRole('button', { name: /^Evans/ }),
    ).not.toBeInTheDocument()
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
    expect(screen.getByRole('button', { name: 'Evans' })).toBeInTheDocument()
  })

  it('updates the counts in place', () => {
    const { update } = renderMap()

    update({ counts: new Map([[2, 3]]) })

    expect(
      screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^Dwinelle/ }),
    ).not.toBeInTheDocument()
    expect(mapbox.maps).toHaveLength(1)
  })

  it("keeps a selected building with no rooms free, until it's deselected", () => {
    const { update } = renderMap({ selectedBuildingId: 2 })

    expect(
      screen.getByRole('button', { name: 'Evans: 0 rooms free' }),
    ).toHaveTextContent('0')

    update({ selectedBuildingId: null })

    expect(
      screen.queryByRole('button', { name: /^Evans/ }),
    ).not.toBeInTheDocument()
  })

  it('keeps a focused marker until focus leaves it', () => {
    const { update } = renderMap({ selectedBuildingId: 2 })
    const evans = screen.getByRole('button', { name: /^Evans/ })
    act(() => evans.focus())

    update({ selectedBuildingId: null })

    expect(
      screen.getByRole('button', { name: 'Evans: 0 rooms free' }),
    ).toHaveAttribute('aria-pressed', 'false')
    expect(evans).toHaveFocus()

    // Switching apps fires focusout but leaves focus here, to come back to.
    fireEvent.focusOut(evans)
    expect(evans).toBeVisible()

    act(() => evans.blur())

    expect(
      screen.queryByRole('button', { name: /^Evans/ }),
    ).not.toBeInTheDocument()
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

  describe('groups', () => {
    const BOTH = new Map([
      [1, 6],
      [2, 3],
    ])
    const GROUP = clusterFeature({ id: 7, buildings: 2, free: 9 })

    /** Has Mapbox show these features, as it does after a move or reload. */
    function show(features: ReturnType<typeof clusterFeature>[]) {
      act(() => {
        mapbox.map.onScreen = features
        mapbox.map.emit('render')
      })
    }

    it('gives Mapbox the buildings to group once the style loads', () => {
      mapbox.styleLoaded = false
      renderMap({ counts: BOTH })
      expect(mapbox.map.addSource).not.toHaveBeenCalled()

      act(() => mapbox.map.emit('style.load'))

      expect(mapbox.map.addSource).toHaveBeenCalledWith(
        'buildings',
        expect.objectContaining({
          type: 'geojson',
          cluster: true,
          clusterMaxZoom: 16,
          clusterProperties: { free: ['+', ['get', 'free']] },
        }),
      )
      expect(mapbox.map.addLayer).toHaveBeenCalledWith(
        expect.objectContaining({ source: 'buildings', type: 'circle' }),
      )
    })

    it('leaves out buildings with none free, and the selected one', () => {
      const { update } = renderMap({ counts: BOTH })
      const source = mapbox.map.getSource('buildings')!
      const grouped = () =>
        source.data.features.map((f) => f.properties.building_id)
      expect(grouped()).toEqual([1, 2])

      update({ counts: new Map([[1, 6]]) })
      expect(grouped()).toEqual([1])

      update({ counts: BOTH, selectedBuildingId: 1 })
      expect(grouped()).toEqual([2])
    })

    it('shows a group with its buildings’ total, in place of them', () => {
      renderMap({ counts: BOTH })

      show([GROUP])

      expect(
        screen.getByRole('button', {
          name: '2 buildings, 9 rooms free. Zoom in',
        }),
      ).toHaveTextContent('9')
      expect(
        screen.queryByRole('button', { name: /^Dwinelle/ }),
      ).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /^Evans/ }),
      ).not.toBeInTheDocument()
    })

    it("shows a group without a number when counts aren't known", () => {
      renderMap({ counts: 'unknown' })

      show([GROUP])

      expect(
        screen.getByRole('button', { name: '2 buildings. Zoom in' }),
      ).toHaveTextContent('')
    })

    it('zooms in to split a group, by click or keyboard', async () => {
      const user = userEvent.setup()
      renderMap({ counts: BOTH })
      show([GROUP])
      const group = screen.getByRole('button', { name: /^2 buildings/ })

      await user.click(group)
      expect(
        mapbox.map.getSource('buildings')!.getClusterExpansionZoom,
      ).toHaveBeenCalledWith(7, expect.any(Function))
      // Not essential, so reduced motion skips the movement.
      expect(mapbox.map.easeTo).toHaveBeenLastCalledWith({
        center: [-122.26, 37.872],
        zoom: 17,
      })

      mapbox.map.easeTo.mockClear()
      group.focus()
      await user.keyboard('{Enter}')
      expect(mapbox.map.easeTo).toHaveBeenCalledTimes(1)
    })

    it('keeps the selected building on its own', () => {
      renderMap({ counts: BOTH, selectedBuildingId: 2 })

      show([clusterFeature({ id: 7, buildings: 3, free: 12 })])

      expect(
        screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
      ).toHaveAttribute('aria-pressed', 'true')
    })

    it('keeps a focused building out of a group until focus leaves', () => {
      renderMap({ counts: BOTH })
      const evans = screen.getByRole('button', { name: /^Evans/ })
      act(() => evans.focus())

      show([GROUP])
      expect(evans).toBeVisible()

      act(() => evans.blur())
      expect(evans).not.toBeVisible()
    })

    it('moves focus to the map once a focused group splits', () => {
      renderMap({ counts: BOTH })
      show([GROUP])
      const group = screen.getByRole('button', { name: /^2 buildings/ })
      act(() => group.focus())

      // Kept while the map zooms in.
      mapbox.map.isMoving.mockReturnValue(true)
      show([pointFeature(DWINELLE, 6), pointFeature(EVANS, 3)])
      expect(group).toHaveFocus()

      mapbox.map.isMoving.mockReturnValue(false)
      act(() => mapbox.map.emit('moveend'))

      expect(group).not.toBeInTheDocument()
      expect(screen.getByRole('region', { name: 'Campus map' })).toHaveFocus()
      expect(screen.getByRole('button', { name: /^Evans/ })).toBeInTheDocument()
    })

    it('updates a group in place', () => {
      const { update } = renderMap({ counts: BOTH })
      show([GROUP])
      const group = screen.getByRole('button', { name: /^2 buildings/ })

      update({ counts: new Map([[1, 6]]) })
      show([clusterFeature({ id: 7, buildings: 2, free: 8 })])

      expect(screen.getByRole('button', { name: /^2 buildings/ })).toBe(group)
      expect(group).toHaveTextContent('8')
    })

    it('keeps the markers while Mapbox reloads the buildings', () => {
      renderMap({ counts: BOTH })
      show([GROUP])

      mapbox.map.isSourceLoaded.mockReturnValue(false)
      show([])

      expect(
        screen.getByRole('button', { name: /^2 buildings/ }),
      ).toBeInTheDocument()
    })

    it('removes groups when the map goes away', () => {
      const { unmount } = renderMap({ counts: BOTH })
      show([GROUP])
      const group = screen.getByRole('button', { name: /^2 buildings/ })

      unmount()

      expect(group).not.toBeInTheDocument()
    })

    it('has accessible groups', async () => {
      const { container } = renderMap({ counts: BOTH })
      show([GROUP])

      await expectNoAxeViolations(container)
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
