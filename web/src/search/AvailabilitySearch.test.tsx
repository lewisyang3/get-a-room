import { StrictMode } from 'react'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AvailabilityPage, AvailabilityResult } from '../api/availability'
import type { Building } from '../api/buildings'
import { expectNoAxeViolations } from '../test/axe'
import { mapbox } from '../test/mapbox'
import AvailabilitySearch from './AvailabilitySearch'

vi.mock('mapbox-gl', async () => (await import('../test/mapbox')).module)

function room(id: number, overrides: Partial<AvailabilityResult> = {}) {
  return {
    room_id: id,
    building_id: 1,
    building_code: 'DWINELLE',
    building_name: 'Dwinelle',
    room_number: String(200 + id),
    available_from: '14:30',
    available_until: '17:00',
    available_minutes: 150,
    distance_meters: null,
    ...overrides,
  }
}

function page(
  results: AvailabilityResult[],
  overrides: Partial<AvailabilityPage> = {},
): AvailabilityPage {
  return {
    total: results.length,
    limit: 50,
    offset: 0,
    date: '2026-10-05',
    day_of_week: 0,
    time: '14:30',
    results,
    ...overrides,
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

type Respond = () => Response | Promise<Response>

const BUILDINGS: Building[] = [
  {
    building_id: 1,
    building_code: 'DWINELLE',
    building_name: 'Dwinelle',
    latitude: null,
    longitude: null,
  },
  {
    building_id: 2,
    building_code: 'EVANS',
    building_name: 'Evans',
    latitude: null,
    longitude: null,
  },
]

/** A /availability/buildings response: [building id, rooms free] pairs. */
function counts(...pairs: [number, number][]) {
  return {
    date: '2026-10-05',
    day_of_week: 0,
    time: '14:30',
    results: pairs.map(([id, free]) => ({
      building_id: id,
      building_code: `B${id}`,
      building_name: `Building ${id}`,
      free_rooms: free,
      longest_free_until: '22:00',
      longest_free_minutes: 450,
      distance_meters: null,
    })),
  }
}

/** Stubs fetch by endpoint. /buildings answers with `buildings`,
 * /availability/buildings with `counts`, and each /availability request takes
 * the next of `availability` in turn. Returns a mock that records only the
 * /availability requests, with the /availability/buildings ones on
 * `.counts`. */
function stubApi({
  buildings = () => jsonResponse({ results: BUILDINGS }),
  availability,
  counts: respondCounts = () => jsonResponse(counts()),
}: {
  buildings?: Respond
  availability: Respond[]
  counts?: Respond
}) {
  // Both take the URL so tests can read it from mock.calls.
  const countsMock = vi.fn(async (_url: string) => respondCounts())
  const availabilityMock = vi.fn(async (_url: string) => {
    const next = availability.shift()
    if (!next) throw new Error('Unexpected request')
    return next()
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const { pathname } = new URL(url)
      if (pathname === '/buildings') return buildings()
      if (pathname === '/availability') return availabilityMock(url)
      if (pathname === '/availability/buildings') return countsMock(url)
      throw new Error(`Unexpected request to ${pathname}`)
    }),
  )
  return Object.assign(availabilityMock, { counts: countsMock })
}

/** Stubs fetch with the default buildings and these /availability
 * responses, in turn. */
function stubResponses(...responses: Respond[]) {
  return stubApi({ availability: responses })
}

/** Waits until the page has asked for the building list. */
async function buildingsLoaded() {
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/buildings$/),
      expect.anything(),
    ),
  )
}

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>, call: number) {
  return new URL(fetchMock.mock.calls[call][0] as string)
}

// Text from the formatters uses non-breaking spaces. toHaveTextContent
// collapses them to plain spaces, but accessible names keep them.
const nbsp = (text: string) => text.replaceAll(' ', ' ')

type GeolocationResult =
  { latitude: number; longitude: number } | 'denied' | 'pending'

/** Gives the page a device location, a refusal, or one that waits for the
 * returned `respond`. jsdom has no navigator.geolocation of its own. */
function stubGeolocation(result: GeolocationResult) {
  let respond: (latitude: number, longitude: number) => void = () => {}
  const getCurrentPosition = vi.fn(
    (
      success: (position: {
        coords: { latitude: number; longitude: number }
      }) => void,
      failure: (error: { code: number; message: string }) => void,
    ) => {
      if (result === 'denied') failure({ code: 1, message: 'User denied' })
      else if (result === 'pending')
        respond = (latitude, longitude) =>
          success({ coords: { latitude, longitude } })
      else success({ coords: result })
    },
  )
  Object.defineProperty(navigator, 'geolocation', {
    value: { getCurrentPosition },
    configurable: true,
  })
  return {
    getCurrentPosition,
    respond: (lat: number, lng: number) => respond(lat, lng),
  }
}

/** Makes the screen wide enough for the map beside the results, or not.
 * jsdom has no matchMedia of its own. */
function stubScreen(width: 'wide' | 'narrow') {
  Object.defineProperty(window, 'matchMedia', {
    value: (query: string) => ({
      matches: width === 'wide' && query === '(min-width: 64rem)',
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
    configurable: true,
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  delete (navigator as { geolocation?: unknown }).geolocation
  delete (window as { matchMedia?: unknown }).matchMedia
  mapbox.reset()
})

describe('AvailabilitySearch', () => {
  it('searches now on load and shows each room', async () => {
    const fetchMock = stubResponses(() =>
      jsonResponse(page([room(1), room(2, { available_minutes: 45 })])),
    )
    render(<AvailabilitySearch termId={3} />)

    expect(
      await screen.findByRole('heading', { name: '2 rooms free now' }),
    ).toBeInTheDocument()
    const url = requestedUrl(fetchMock, 0)
    expect(url.searchParams.get('term_id')).toBe('3')
    expect(url.searchParams.has('at')).toBe(false)

    // GAR-034: building, room, availability start and end, and duration.
    const group = screen.getByRole('region', { name: 'Dwinelle' })
    const rows = within(group).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Room 201')
    expect(rows[0]).toHaveTextContent('Free 2:30 PM – 5:00 PM')
    expect(rows[0]).toHaveTextContent('2 h 30 min')
    expect(rows[1]).toHaveTextContent('45 min')
    // Every building is shown, so there's nothing to clear.
    expect(
      screen.queryByRole('button', { name: 'Show all buildings' }),
    ).toBeNull()
  })

  it('still searches when StrictMode mounts effects twice', async () => {
    stubResponses(
      () => jsonResponse(page([room(1)])),
      () => jsonResponse(page([room(1)])),
    )
    render(
      <StrictMode>
        <AvailabilitySearch termId={3} />
      </StrictMode>,
    )

    expect(
      await screen.findByRole('heading', { name: '1 room free now' }),
    ).toBeInTheDocument()
  })

  it('shows a loading state before the first results arrive', async () => {
    let respond: (response: Response) => void = () => {}
    stubResponses(() => new Promise<Response>((resolve) => (respond = resolve)))
    render(<AvailabilitySearch termId={3} />)

    expect(screen.getByRole('status')).toHaveTextContent('Finding rooms…')

    respond(jsonResponse(page([room(1)])))
    expect(
      await screen.findByRole('heading', { name: '1 room free now' }),
    ).toBeInTheDocument()
  })

  it('explains an empty result', async () => {
    stubResponses(() => jsonResponse(page([])))
    render(<AvailabilitySearch termId={3} />)

    expect(
      await screen.findByRole('heading', { name: 'No rooms free now' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/covers 7\sa\.m\. to 10\sp\.m\./),
    ).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('shows an error and retries the search', async () => {
    const user = userEvent.setup()
    const fetchMock = stubResponses(
      () => jsonResponse({}, 503),
      () => jsonResponse(page([room(1)])),
    )
    render(<AvailabilitySearch termId={3} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong with that search.',
    )
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(
      await screen.findByRole('heading', { name: '1 room free now' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  describe('minimum duration filter', () => {
    it('defaults to an hour', async () => {
      const fetchMock = stubResponses(() => jsonResponse(page([room(1)])))
      render(<AvailabilitySearch termId={3} />)

      await screen.findByRole('heading', { name: '1 room free now' })
      expect(screen.getByRole('radio', { name: nbsp('1 h') })).toBeChecked()
      expect(
        requestedUrl(fetchMock, 0).searchParams.get('minimum_minutes'),
      ).toBe('60')
      expect(screen.getByText('For at least an hour')).toBeInTheDocument()
    })

    it('updates the results as soon as it changes', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1), room(2)])),
        () => jsonResponse(page([room(2)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.click(screen.getByRole('radio', { name: nbsp('2 h') }))

      expect(
        await screen.findByRole('heading', { name: '1 room free now' }),
      ).toBeInTheDocument()
      expect(screen.getByText('For at least 2 hours')).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 1)
      expect(url.searchParams.get('minimum_minutes')).toBe('120')
      expect(url.searchParams.has('at')).toBe(false)
    })

    it('describes the shown results while a new minimum loads', async () => {
      const user = userEvent.setup()
      let respond: (response: Response) => void = () => {}
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => new Promise<Response>((resolve) => (respond = resolve)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: nbsp('3 h') }))
      expect(screen.getByText('For at least an hour')).toBeInTheDocument()

      respond(jsonResponse(page([])))
      expect(
        await screen.findByText(/^Nothing is free for at least 3 hours now\./),
      ).toBeInTheDocument()
    })
  })

  describe('building groups', () => {
    const evans = (id: number, overrides: Partial<AvailabilityResult> = {}) =>
      room(id, {
        building_id: 2,
        building_code: 'EVANS',
        building_name: 'Evans',
        ...overrides,
      })

    it("lists each building's rooms under its name, in order", async () => {
      stubResponses(() =>
        jsonResponse(page([room(1), room(2), evans(3), evans(4)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '4 rooms free now' })

      expect(
        screen
          .getAllByRole('heading', { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(['Dwinelle', 'Evans'])
      const evansGroup = screen.getByRole('region', { name: 'Evans' })
      expect(within(evansGroup).getAllByRole('listitem')).toHaveLength(2)
      expect(evansGroup).toHaveTextContent('Room 203')
    })

    it('keeps a building split across pages in one group', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse(page([room(1), evans(2)], { total: 3 })),
        () => jsonResponse(page([evans(3)], { total: 3, offset: 2 })),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByText('Showing 2 of 3')

      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await screen.findByText('Room 203')

      const evansGroup = screen.getByRole('region', { name: 'Evans' })
      expect(within(evansGroup).getAllByRole('listitem')).toHaveLength(2)
      expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(2)
    })

    it("shows the distance and directions when they're known", async () => {
      stubApi({
        buildings: () =>
          jsonResponse({
            results: [
              { ...BUILDINGS[0] },
              { ...BUILDINGS[1], latitude: 37.87362, longitude: -122.25768 },
            ],
          }),
        availability: [
          () =>
            jsonResponse(
              page([
                room(1, { distance_meters: null }),
                evans(2, { distance_meters: 416 }),
              ]),
            ),
        ],
      })
      render(<AvailabilitySearch termId={3} />)

      const link = await screen.findByRole('link', {
        name: 'Directions to Evans (opens in a new tab)',
      })
      const url = new URL(link.getAttribute('href') ?? '')
      expect(url.origin + url.pathname).toBe('https://www.google.com/maps/dir/')
      expect(url.searchParams.get('destination')).toBe('37.87362,-122.25768')
      expect(url.searchParams.get('travelmode')).toBe('walking')
      expect(link).toHaveAttribute('target', '_blank')
      expect(screen.getByRole('region', { name: 'Evans' })).toHaveTextContent(
        '0.3 mi',
      )
      // Dwinelle's location is unknown, so it has no distance or directions.
      const dwinelle = screen.getByRole('region', { name: 'Dwinelle' })
      expect(within(dwinelle).queryByRole('link')).not.toBeInTheDocument()
      expect(dwinelle).not.toHaveTextContent(/\bmi\b/)
    })
  })

  describe('nearest sort', () => {
    const LOCATED_BUILDINGS = () =>
      jsonResponse({
        results: [
          { ...BUILDINGS[0], latitude: 37.87073, longitude: -122.26074 },
          { ...BUILDINGS[1], latitude: 37.87362, longitude: -122.25768 },
        ],
      })
    const evans = (id: number, distance: number | null) =>
      room(id, {
        building_id: 2,
        building_code: 'EVANS',
        building_name: 'Evans',
        distance_meters: distance,
      })
    const sortGroup = () => screen.findByRole('group', { name: 'Sort' })

    it('sorts by the rounded device location', async () => {
      const user = userEvent.setup()
      stubGeolocation({ latitude: 37.87362, longitude: -122.25768 })
      const fetchMock = stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1), evans(2, null)])),
          () =>
            jsonResponse(
              page([evans(2, 3), room(1, { distance_meters: 416 })]),
            ),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.click(
        within(await sortGroup()).getByRole('radio', { name: 'Nearest' }),
      )

      expect(
        await screen.findByText('For at least an hour · Nearest first'),
      ).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 1)
      // Rounded to about 100 m before it's sent.
      expect(url.searchParams.get('near_latitude')).toBe('37.874')
      expect(url.searchParams.get('near_longitude')).toBe('-122.258')
      expect(
        screen
          .getAllByRole('heading', { level: 3 })
          .map((heading) => heading.textContent),
      ).toEqual(['Evans', 'Dwinelle'])
      expect(screen.getByRole('region', { name: 'Evans' })).toHaveTextContent(
        'Under 0.1 mi',
      )
      expect(
        screen.getByRole('region', { name: 'Dwinelle' }),
      ).toHaveTextContent('0.3 mi')
    })

    it('says while it finds the location', async () => {
      const user = userEvent.setup()
      const geolocation = stubGeolocation('pending')
      stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1)])),
          () => jsonResponse(page([room(1, { distance_meters: 416 })])),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })
      const group = await sortGroup()

      await user.click(within(group).getByRole('radio', { name: 'Nearest' }))

      expect(within(group).getByRole('status')).toHaveTextContent(
        'Finding your location…',
      )
      expect(
        within(group).getByRole('radio', { name: 'Nearest' }),
      ).toBeChecked()

      geolocation.respond(37.87073, -122.26074)
      expect(
        await screen.findByText('For at least an hour · Nearest first'),
      ).toBeInTheDocument()
      expect(within(group).getByRole('status')).toHaveTextContent('')
    })

    it('goes back to sorting by building when the location is refused', async () => {
      const user = userEvent.setup()
      stubGeolocation('denied')
      const fetchMock = stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [() => jsonResponse(page([room(1)]))],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })
      const group = await sortGroup()

      await user.click(within(group).getByRole('radio', { name: 'Nearest' }))

      expect(
        await within(group).findByText(
          "Couldn't get your location, so rooms are sorted by building.",
        ),
      ).toBeInTheDocument()
      expect(
        within(group).getByRole('radio', { name: 'Building' }),
      ).toBeChecked()
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    it('is left out when location or building locations are unavailable', async () => {
      // No navigator.geolocation.
      stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [() => jsonResponse(page([room(1)]))],
      })
      const { unmount } = render(<AvailabilitySearch termId={3} />)
      await buildingsLoaded()
      expect(
        screen.queryByRole('group', { name: 'Sort' }),
      ).not.toBeInTheDocument()
      unmount()

      // No building has coordinates.
      stubGeolocation({ latitude: 37.87, longitude: -122.26 })
      stubResponses(() => jsonResponse(page([room(1)])))
      render(<AvailabilitySearch termId={3} />)
      await buildingsLoaded()
      expect(
        screen.queryByRole('group', { name: 'Sort' }),
      ).not.toBeInTheDocument()
    })

    it('keeps sorting by distance when showing more and trying again', async () => {
      const user = userEvent.setup()
      stubGeolocation({ latitude: 37.87362, longitude: -122.25768 })
      const fetchMock = stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1)])),
          () => jsonResponse({}, 503),
          () => jsonResponse(page([evans(2, 3), evans(3, 3)], { total: 3 })),
          () =>
            jsonResponse(
              page([room(4, { distance_meters: null })], {
                total: 3,
                offset: 2,
              }),
            ),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(
        within(await sortGroup()).getByRole('radio', { name: 'Nearest' }),
      )
      await screen.findByRole('alert')
      await user.click(screen.getByRole('button', { name: 'Try again' }))
      await screen.findByText('Showing 2 of 3')
      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await screen.findByText('Room 204')

      for (const call of [2, 3]) {
        expect(
          requestedUrl(fetchMock, call).searchParams.get('near_latitude'),
        ).toBe('37.874')
      }
      // Sorted by distance, a building with no location says so.
      expect(
        screen.getByRole('region', { name: 'Dwinelle' }),
      ).toHaveTextContent('Location unknown')
    })

    it('stops sorting by distance when Building is chosen', async () => {
      const user = userEvent.setup()
      const geolocation = stubGeolocation({
        latitude: 37.87362,
        longitude: -122.25768,
      })
      const fetchMock = stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1)])),
          () => jsonResponse(page([room(1, { distance_meters: 416 })])),
          () => jsonResponse(page([room(1)])),
          () => jsonResponse(page([room(1, { distance_meters: 416 })])),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })
      const group = await sortGroup()

      await user.click(within(group).getByRole('radio', { name: 'Nearest' }))
      await screen.findByText('For at least an hour · Nearest first')
      await user.click(within(group).getByRole('radio', { name: 'Building' }))

      await screen.findByText('For at least an hour')
      expect(requestedUrl(fetchMock, 2).searchParams.has('near_latitude')).toBe(
        false,
      )

      // Choosing Nearest again reuses the location instead of asking again.
      await user.click(within(group).getByRole('radio', { name: 'Nearest' }))
      await screen.findByText('For at least an hour · Nearest first')
      expect(geolocation.getCurrentPosition).toHaveBeenCalledTimes(1)
    })
  })

  describe('room or building search', () => {
    const searchField = () =>
      screen.getByRole('searchbox', { name: 'Room or building' })

    it('searches once typing pauses', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1), room(42)])),
        () => jsonResponse(page([room(42)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.type(searchField(), 'Dwinelle 242')

      expect(
        await screen.findByRole('heading', {
          name: '1 room free now matching “Dwinelle 242”',
        }),
      ).toBeInTheDocument()
      // One search for the whole text, not one per keystroke.
      expect(fetchMock).toHaveBeenCalledTimes(2)
      const url = requestedUrl(fetchMock, 1)
      expect(url.searchParams.get('building')).toBe('Dwinelle')
      expect(url.searchParams.get('room')).toBe('242')
    })

    it.each([
      ['242', { room: '242', building: null }],
      ['dwin', { room: null, building: 'dwin' }],
    ])('reads %s', async (text, expected) => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.type(searchField(), text)

      await screen.findByRole('heading', { name: /matching/ })
      const url = requestedUrl(fetchMock, 1)
      expect(url.searchParams.get('room')).toBe(expected.room)
      expect(url.searchParams.get('building')).toBe(expected.building)
    })

    it('applies together with the other filters', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: nbsp('2 h') }))
      await screen.findByText(/^For at least 2 hours/)
      await user.type(searchField(), '101')

      expect(
        await screen.findByRole('heading', {
          name: 'No rooms free now matching “101”',
        }),
      ).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 2)
      expect(url.searchParams.get('minimum_minutes')).toBe('120')
      expect(url.searchParams.get('room')).toBe('101')
    })

    it('searches right away when submitted with Enter', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.type(searchField(), '  Evans ')
      // Enter submits the form in browsers: the search field is its only text
      // field. user-event only does so for a form with one input of any type,
      // and the duration radios are inputs, so this submits the form directly.
      fireEvent.submit(screen.getByRole('form', { name: 'Search' }))

      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(requestedUrl(fetchMock, 1).searchParams.get('building')).toBe(
        'Evans',
      )
      await screen.findByRole('heading', {
        name: '1 room free now matching “Evans”',
      })
      // The pause after typing has nothing left to apply.
      await new Promise((resolve) => setTimeout(resolve, 400))
      expect(fetchMock).toHaveBeenCalledTimes(2)
    })

    it('shows every room again when cleared', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1), room(2)])),
        () => jsonResponse(page([room(2)])),
        () => jsonResponse(page([room(1), room(2)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '2 rooms free now' })
      await user.type(searchField(), '202')
      await screen.findByRole('heading', { name: /matching “202”/ })

      await user.clear(searchField())

      expect(
        await screen.findByRole('heading', { name: '2 rooms free now' }),
      ).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 2)
      expect(url.searchParams.has('room')).toBe(false)
      expect(url.searchParams.has('building')).toBe(false)
    })

    it('says when nothing matches', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.type(searchField(), 'Dwinelle 999')

      expect(
        await screen.findByRole('heading', {
          name: 'No rooms free now matching “Dwinelle 999”',
        }),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          /^No free room matches “Dwinelle 999” for at least an hour now\. Check the room number/,
        ),
      ).toBeInTheDocument()
    })

    it('describes the shown results while a new search loads', async () => {
      const user = userEvent.setup()
      let respond: (response: Response) => void = () => {}
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
        () => new Promise<Response>((resolve) => (respond = resolve)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })
      await user.type(searchField(), 'Dwinelle')
      await screen.findByRole('heading', {
        name: '1 room free now matching “Dwinelle”',
      })

      await user.type(searchField(), ' 201')
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { level: 2 }).closest('[aria-busy]'),
        ).toHaveAttribute('aria-busy', 'true'),
      )
      expect(
        screen.getByRole('heading', {
          name: '1 room free now matching “Dwinelle”',
        }),
      ).toBeInTheDocument()

      respond(jsonResponse(page([room(1)])))
      expect(
        await screen.findByRole('heading', {
          name: '1 room free now matching “Dwinelle 201”',
        }),
      ).toBeInTheDocument()
    })

    it('keeps the search when showing more and trying again', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse({}, 503),
        () => jsonResponse(page([room(1), room(2)], { total: 3 })),
        () => jsonResponse(page([room(3)], { total: 3, offset: 2 })),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.type(searchField(), 'dwin')
      await screen.findByRole('alert')
      await user.click(screen.getByRole('button', { name: 'Try again' }))
      await screen.findByText('Showing 2 of 3')
      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await screen.findByText('Room 203')

      expect(requestedUrl(fetchMock, 2).searchParams.get('building')).toBe(
        'dwin',
      )
      expect(requestedUrl(fetchMock, 3).searchParams.get('building')).toBe(
        'dwin',
      )
    })
  })

  it.each([
    [
      'a failed connection',
      () => {
        throw new TypeError('Failed to fetch')
      },
      "Couldn't reach Get a Room.",
    ],
    [
      'a missing term',
      () => jsonResponse({}, 404),
      "This term isn't available.",
    ],
  ])('explains %s', async (_, respond, message) => {
    stubResponses(respond)
    render(<AvailabilitySearch termId={3} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it('loads more rooms', async () => {
    const user = userEvent.setup()
    const fetchMock = stubResponses(
      () => jsonResponse(page([room(1), room(2)], { total: 3 })),
      () => jsonResponse(page([room(3)], { total: 3, offset: 2 })),
    )
    render(<AvailabilitySearch termId={3} />)

    expect(await screen.findByText('Showing 2 of 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show more' }))

    await screen.findByText('Room 203')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(requestedUrl(fetchMock, 1).searchParams.get('offset')).toBe('2')
    expect(
      screen.queryByRole('button', { name: 'Show more' }),
    ).not.toBeInTheDocument()
  })

  it("doesn't search when no term is configured", () => {
    stubResponses()
    render(<AvailabilitySearch termId={null} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      "Search isn't set up yet",
    )
    expect(fetch).not.toHaveBeenCalled()
  })

  // GAR-038: Show more and Try again go away once they've done their job, so
  // focus moves on rather than dropping to the page.
  describe('focus', () => {
    it('moves to the first new room after Show more', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse(page([room(1), room(2)], { total: 5 })),
        () => jsonResponse(page([room(3), room(4)], { total: 5, offset: 2 })),
        () => jsonResponse(page([room(5)], { total: 5, offset: 4 })),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByText('Showing 2 of 5')

      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await waitFor(() =>
        expect(screen.getAllByRole('listitem')[2]).toHaveFocus(),
      )
      expect(document.activeElement).toHaveTextContent('Room 203')

      // The last page removes the button, and focus still lands on a room.
      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await waitFor(() =>
        expect(screen.getAllByRole('listitem')[4]).toHaveFocus(),
      )
      expect(
        screen.queryByRole('button', { name: 'Show more' }),
      ).not.toBeInTheDocument()
    })

    it("returns to the button when more rooms can't load", async () => {
      const user = userEvent.setup()
      let respond: (response: Response) => void = () => {}
      stubResponses(
        () => jsonResponse(page([room(1)], { total: 2 })),
        () => new Promise<Response>((resolve) => (respond = resolve)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByText('Showing 1 of 2')

      await user.click(screen.getByRole('button', { name: 'Show more' }))
      const button = screen.getByRole('button', { name: 'Loading…' })
      expect(button).toBeDisabled()
      // Browsers move focus off a button once it's disabled. jsdom doesn't,
      // and its blur() ignores disabled elements, so park focus on an element
      // and remove it, which leaves focus on the page.
      const parked = document.createElement('div')
      parked.tabIndex = -1
      document.body.append(parked)
      parked.focus()
      parked.remove()
      expect(document.body).toHaveFocus()
      respond(jsonResponse({}, 503))

      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Try again' })).toHaveFocus(),
      )
    })

    it('moves to the results after Try again', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse({}, 503),
        () => jsonResponse({}, 503),
        () => jsonResponse(page([room(1)])),
      )
      render(<AvailabilitySearch termId={3} />)

      await user.click(await screen.findByRole('button', { name: 'Try again' }))
      // Failed again: the new Try again button takes focus.
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Try again' })).toHaveFocus(),
      )

      await user.click(screen.getByRole('button', { name: 'Try again' }))
      const heading = await screen.findByRole('heading', {
        name: '1 room free now',
      })
      await waitFor(() => expect(heading).toHaveFocus())
    })

    it("doesn't move focus when a filter changes during Try again", async () => {
      const user = userEvent.setup()
      let respond: (response: Response) => void = () => {}
      stubResponses(
        () => jsonResponse({}, 503),
        () => new Promise<Response>(() => {}),
        () => new Promise<Response>((resolve) => (respond = resolve)),
      )
      render(<AvailabilitySearch termId={3} />)

      await user.click(await screen.findByRole('button', { name: 'Try again' }))
      // A new search replaces the retry before it finishes.
      const option = screen.getByRole('radio', { name: nbsp('30 min') })
      await user.click(option)
      respond(jsonResponse(page([room(1)])))
      await screen.findByRole('heading', { name: '1 room free now' })

      expect(option).toHaveFocus()
    })

    it('stays on a filter when it changes the results', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1), room(2)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      const option = screen.getByRole('radio', { name: nbsp('30 min') })
      await user.click(option)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      expect(option).toHaveFocus()
    })
  })

  // GAR-038: each state passes axe. The component is rendered without the
  // page's landmarks, so the region rule is left to the landing page test.
  describe('campus map', () => {
    const LOCATED = () =>
      jsonResponse({
        results: [
          { ...BUILDINGS[0], latitude: 37.87073, longitude: -122.26074 },
          { ...BUILDINGS[1], latitude: 37.87362, longitude: -122.25768 },
        ],
      })
    const evans = (id: number) =>
      room(id, {
        building_id: 2,
        building_code: 'EVANS',
        building_name: 'Evans',
      })
    const withMap = (availability: Respond[]) =>
      stubApi({
        buildings: LOCATED,
        availability,
        counts: () => jsonResponse(counts([1, 2], [2, 3])),
      })

    it('is left out without a Mapbox token', async () => {
      stubScreen('wide')
      const fetchMock = stubApi({
        buildings: LOCATED,
        availability: [() => jsonResponse(page([room(1)]))],
      })
      render(<AvailabilitySearch termId={3} mapboxToken={null} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      expect(screen.queryByRole('region', { name: 'Campus map' })).toBeNull()
      expect(screen.queryByRole('group', { name: 'Show' })).toBeNull()
      expect(fetchMock.counts).not.toHaveBeenCalled()
    })

    it('is left out when no building has a location', async () => {
      stubScreen('wide')
      stubResponses(() => jsonResponse(page([room(1)])))
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '1 room free now' })

      expect(screen.queryByRole('region', { name: 'Campus map' })).toBeNull()
    })

    it('shows each building with its count beside the results', async () => {
      stubScreen('wide')
      const fetchMock = withMap([() => jsonResponse(page([room(1)]))])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)

      expect(
        await screen.findByRole('button', { name: 'Evans: 3 rooms free' }),
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Dwinelle: 2 rooms free' }),
      ).toBeInTheDocument()
      // The list shows alongside, with no switch.
      expect(
        screen.getByRole('heading', { name: '1 room free now' }),
      ).toBeVisible()
      expect(screen.queryByRole('group', { name: 'Show' })).toBeNull()
      // Counted at the minute the list shows, across every building.
      const url = new URL(fetchMock.counts.mock.calls[0][0])
      expect(url.searchParams.get('at')).toBe('2026-10-05T14:30')
      expect(url.searchParams.has('building_id')).toBe(false)
    })

    it('filters the results to a building chosen on the map, and back', async () => {
      const user = userEvent.setup()
      stubScreen('wide')
      const fetchMock = withMap([
        () => jsonResponse(page([room(1), evans(2)])),
        () => jsonResponse(page([evans(2)])),
        () => jsonResponse(page([room(1), evans(2)])),
      ])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.click(
        await screen.findByRole('button', { name: 'Evans: 3 rooms free' }),
      )

      expect(
        await screen.findByRole('heading', {
          name: '1 room free now in Evans',
        }),
      ).toBeInTheDocument()
      expect(requestedUrl(fetchMock, 1).searchParams.get('building_id')).toBe(
        '2',
      )
      expect(
        screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
      ).toHaveAttribute('aria-pressed', 'true')

      await user.click(
        screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
      )

      expect(
        await screen.findByRole('heading', { name: '2 rooms free now' }),
      ).toBeInTheDocument()
    })

    it('clears a building chosen on the map with Show all buildings', async () => {
      const user = userEvent.setup()
      stubScreen('wide')
      const fetchMock = withMap([
        () => jsonResponse(page([room(1), evans(2)])),
        () => jsonResponse(page([evans(2)])),
        () => jsonResponse(page([room(1), evans(2)])),
      ])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.click(
        await screen.findByRole('button', { name: 'Evans: 3 rooms free' }),
      )
      await screen.findByRole('heading', { name: '1 room free now in Evans' })
      await expectNoAxeViolations(document.body, { region: false })

      await user.click(
        screen.getByRole('button', { name: 'Show all buildings' }),
      )

      const heading = await screen.findByRole('heading', {
        name: '2 rooms free now',
      })
      expect(requestedUrl(fetchMock, 2).searchParams.has('building_id')).toBe(
        false,
      )
      expect(
        screen.getByRole('button', { name: 'Evans: 3 rooms free' }),
      ).toHaveAttribute('aria-pressed', 'false')
      expect(
        screen.queryByRole('button', { name: 'Show all buildings' }),
      ).toBeNull()
      // The button went away, so focus moves to the results.
      await waitFor(() => expect(heading).toHaveFocus())
    })

    it('clears the building from the list on a narrow screen', async () => {
      const user = userEvent.setup()
      stubScreen('narrow')
      withMap([
        () => jsonResponse(page([room(1), evans(2)])),
        () => jsonResponse(page([evans(2)])),
        () => jsonResponse(page([room(1), evans(2)])),
      ])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '2 rooms free now' })
      await user.click(screen.getByRole('radio', { name: 'Map' }))
      await user.click(
        await screen.findByRole('button', { name: 'Evans: 3 rooms free' }),
      )
      await screen.findByRole('heading', { name: '1 room free now in Evans' })

      // Back on the list, without going to the map again.
      await user.click(
        screen.getByRole('button', { name: 'Show all buildings' }),
      )

      expect(
        await screen.findByRole('heading', { name: '2 rooms free now' }),
      ).toBeVisible()
      expect(screen.getByRole('region', { name: 'Dwinelle' })).toBeVisible()
      expect(screen.getByRole('region', { name: 'Evans' })).toBeVisible()
      expect(screen.queryByRole('region', { name: 'Campus map' })).toBeNull()
    })

    it('switches between the list and the map on a narrow screen', async () => {
      const user = userEvent.setup()
      stubScreen('narrow')
      withMap([
        () => jsonResponse(page([room(1), evans(2)])),
        () => jsonResponse(page([evans(2)])),
      ])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '2 rooms free now' })
      // The map loads only when it's shown.
      expect(mapbox.maps).toHaveLength(0)

      await user.click(screen.getByRole('radio', { name: 'Map' }))

      expect(
        await screen.findByRole('region', { name: 'Campus map' }),
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('heading', { name: '2 rooms free now' }),
      ).toBeNull()

      // Choosing a building goes back to the list, showing its rooms.
      await user.click(
        await screen.findByRole('button', { name: 'Evans: 3 rooms free' }),
      )

      expect(
        await screen.findByRole('heading', {
          name: '1 room free now in Evans',
        }),
      ).toBeVisible()
      expect(screen.getByRole('radio', { name: 'List' })).toBeChecked()
      expect(screen.queryByRole('region', { name: 'Campus map' })).toBeNull()
    })

    it("falls back to the list when the map can't run", async () => {
      const user = userEvent.setup()
      stubScreen('narrow')
      mapbox.supported = false
      withMap([() => jsonResponse(page([room(1)]))])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: 'Map' }))

      expect(
        await screen.findByRole('heading', { name: '1 room free now' }),
      ).toBeVisible()
      expect(screen.queryByRole('group', { name: 'Show' })).toBeNull()
    })

    it('has no accessibility violations beside the results', async () => {
      stubScreen('wide')
      withMap([() => jsonResponse(page([room(1), evans(2)]))])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('button', { name: 'Evans: 3 rooms free' })

      await expectNoAxeViolations(document.body, { region: false })
    })

    it('has no accessibility violations with the switch on a narrow screen', async () => {
      stubScreen('narrow')
      withMap([() => jsonResponse(page([room(1)]))])
      render(<AvailabilitySearch termId={3} mapboxToken="pk.test" />)
      await screen.findByRole('radio', { name: 'Map' })

      await expectNoAxeViolations(document.body, { region: false })
    })
  })

  describe('accessibility', () => {
    const check = () => expectNoAxeViolations(document.body, { region: false })
    const LOCATED_BUILDINGS = () =>
      jsonResponse({
        results: [
          { ...BUILDINGS[0], latitude: 37.87073, longitude: -122.26074 },
          { ...BUILDINGS[1], latitude: 37.87362, longitude: -122.25768 },
        ],
      })
    const evans = (id: number, overrides: Partial<AvailabilityResult> = {}) =>
      room(id, {
        building_id: 2,
        building_code: 'EVANS',
        building_name: 'Evans',
        ...overrides,
      })

    it('while the first search loads', async () => {
      stubResponses(() => new Promise<Response>(() => {}))
      render(<AvailabilitySearch termId={3} />)
      await buildingsLoaded()

      await check()
    })

    it('with results in groups, directions and Show more', async () => {
      stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1), room(2), evans(3)], { total: 60 })),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('link', { name: /Directions to Evans/ })
      await screen.findByRole('button', { name: 'Show more' })

      await check()
    })

    it('with no results', async () => {
      stubResponses(() => jsonResponse(page([])))
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: 'No rooms free now' })

      await check()
    })

    it('with an error', async () => {
      stubResponses(() => jsonResponse({}, 503))
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('button', { name: 'Try again' })

      await check()
    })

    it('when sorted by nearest', async () => {
      const user = userEvent.setup()
      stubGeolocation({ latitude: 37.87362, longitude: -122.25768 })
      stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [
          () => jsonResponse(page([room(1), evans(2)])),
          () =>
            jsonResponse(
              page([
                evans(2, { distance_meters: 3 }),
                room(1, { distance_meters: 416 }),
              ]),
            ),
        ],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '2 rooms free now' })

      await user.click(await screen.findByRole('radio', { name: 'Nearest' }))
      await screen.findByText('For at least an hour · Nearest first')

      await check()
    })

    it("when the location can't be found", async () => {
      const user = userEvent.setup()
      stubGeolocation('denied')
      stubApi({
        buildings: LOCATED_BUILDINGS,
        availability: [() => jsonResponse(page([room(1)]))],
      })
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(await screen.findByRole('radio', { name: 'Nearest' }))
      await screen.findByText(/Couldn't get your location/)

      await check()
    })
  })
})
