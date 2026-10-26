import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Building } from '../api/buildings'
import { expectNoAxeViolations } from '../test/axe'
import { mapbox } from '../test/mapbox'
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
// Near Dwinelle and Evans, to group with them.
const DOE: LocatedBuilding = {
  building_id: 4,
  building_code: 'DOE',
  building_name: 'Doe Library',
  latitude: 37.8722,
  longitude: -122.2594,
}
// Far enough from the others not to group with them.
const LAWRENCE: LocatedBuilding = {
  building_id: 5,
  building_code: 'LHS',
  building_name: 'Lawrence Hall of Science',
  latitude: 37.8793,
  longitude: -122.2465,
}
const NOWHERE: Building = {
  building_id: 3,
  building_code: 'HFA',
  building_name: 'Hearst Field Annex',
  latitude: null,
  longitude: null,
}

function renderMap({
  buildings = [DWINELLE, EVANS, NOWHERE] as Building[],
  counts = new Map([[1, 6]]) as FreeRoomCounts,
  selectedBuildingId = null as number | null,
  onSelect = vi.fn(),
  onUnavailable = vi.fn(),
} = {}) {
  const props = {
    token: 'pk.test',
    buildings,
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

    // Switching apps fires blur but leaves focus here, to come back to.
    fireEvent.blur(evans)
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

    /** Zooms the map out until Dwinelle and Evans group, or back in. */
    function zoomTo(zoom: number) {
      act(() => {
        mapbox.map.zoom = zoom
        mapbox.map.emit('moveend')
      })
    }

    const group = () => screen.getByRole('button', { name: /^2 buildings/ })

    it('shows nearby buildings as one group with their total', () => {
      renderMap({ counts: BOTH })

      zoomTo(12)

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

    it('shows the buildings before the style loads', () => {
      renderMap({ counts: BOTH })

      // No 'style.load' or 'moveend' yet.
      expect(
        screen.getByRole('button', { name: /^Dwinelle/ }),
      ).toBeInTheDocument()
    })

    it("shows a group without a number when counts aren't known", () => {
      renderMap({ counts: 'unknown' })

      zoomTo(12)

      expect(
        screen.getByRole('button', { name: '2 buildings. Zoom in' }),
      ).toHaveTextContent('')
    })

    it('shows the right total as soon as counts change', () => {
      const { update } = renderMap({ counts: 'unknown' })
      zoomTo(12)
      const before = group()

      update({ counts: BOTH })

      expect(group()).toBe(before)
      expect(group()).toHaveTextContent('9')
    })

    it('zooms in to split a group, by click or keyboard', async () => {
      const user = userEvent.setup()
      renderMap({ counts: BOTH })
      zoomTo(12)

      await user.click(group())
      // Not essential, so reduced motion skips the movement.
      expect(mapbox.map.easeTo).toHaveBeenLastCalledWith({
        center: [expect.any(Number), expect.any(Number)],
        zoom: expect.any(Number),
      })
      expect(mapbox.map.easeTo.mock.lastCall![0].zoom).toBeGreaterThan(12)

      mapbox.map.easeTo.mockClear()
      act(() => group().focus())
      await user.keyboard('{Enter}')
      // Again while the map is still moving, as it would be.
      await user.keyboard('{Enter}')
      expect(mapbox.map.easeTo).toHaveBeenCalledTimes(2)
    })

    it('keeps the selected building on its own', () => {
      renderMap({ counts: BOTH, selectedBuildingId: 2 })

      zoomTo(12)

      expect(
        screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
      ).toHaveAttribute('aria-pressed', 'true')
      expect(
        screen.queryByRole('button', { name: /buildings/ }),
      ).not.toBeInTheDocument()
    })

    it('keeps a focused building out of groups until focus leaves', () => {
      renderMap({
        buildings: [DWINELLE, EVANS, DOE],
        counts: new Map([
          [1, 6],
          [2, 3],
          [4, 2],
        ]),
      })
      const evansButton = screen.getByRole('button', { name: /^Evans/ })
      act(() => evansButton.focus())

      zoomTo(12)

      // Evans on its own, and not counted in the group too.
      expect(evansButton).toBeVisible()
      expect(
        screen.getByRole('button', {
          name: '2 buildings, 8 rooms free. Zoom in',
        }),
      ).toBeInTheDocument()

      act(() => evansButton.blur())
      expect(evansButton).not.toBeVisible()
      expect(
        screen.getByRole('button', {
          name: '3 buildings, 11 rooms free. Zoom in',
        }),
      ).toBeInTheDocument()
    })

    it('moves focus to the map, without scrolling, when a focused group splits', () => {
      renderMap({ counts: BOTH })
      zoomTo(12)
      const focused = group()
      act(() => focused.focus())
      const region = screen.getByRole('region', { name: 'Campus map' })
      const focus = vi.spyOn(region, 'focus')

      zoomTo(16)

      expect(focused).not.toBeInTheDocument()
      expect(region).toHaveFocus()
      expect(focus).toHaveBeenCalledWith({ preventScroll: true })
      expect(screen.getByRole('button', { name: /^Evans/ })).toBeInTheDocument()
    })

    it('keeps a group’s button while focus moves between buildings', () => {
      renderMap({
        buildings: [DWINELLE, EVANS, LAWRENCE],
        counts: new Map([...BOTH, [5, 1]]),
      })
      zoomTo(12)
      const before = group()
      const lawrence = screen.getByRole('button', { name: /^Lawrence/ })

      // Each regroups the buildings, without and then with Lawrence.
      act(() => lawrence.focus())
      expect(group()).toBe(before)
      act(() => lawrence.blur())
      expect(group()).toBe(before)
    })

    it('removes groups when the map goes away', () => {
      const { unmount } = renderMap({ counts: BOTH })
      zoomTo(12)
      const shown = group()

      unmount()

      expect(shown).not.toBeInTheDocument()
    })

    it('has accessible groups', async () => {
      const { container } = renderMap({ counts: BOTH })
      zoomTo(12)

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
