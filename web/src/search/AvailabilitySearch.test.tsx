import { StrictMode } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AvailabilityPage, AvailabilityResult } from '../api/availability'
import type { Building } from '../api/buildings'
import AvailabilitySearch from './AvailabilitySearch'

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

/** Stubs fetch by endpoint. /buildings answers with `buildings`, and each
 * /availability request takes the next of `availability` in turn. Returns a
 * mock that records only the /availability requests. */
function stubApi({
  buildings = () => jsonResponse({ results: BUILDINGS }),
  availability,
}: {
  buildings?: Respond
  availability: Respond[]
}) {
  // Takes the URL so tests can read it from mock.calls.
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
      throw new Error(`Unexpected request to ${pathname}`)
    }),
  )
  return availabilityMock
}

/** Stubs fetch with the default buildings and these /availability
 * responses, in turn. */
function stubResponses(...responses: Respond[]) {
  return stubApi({ availability: responses })
}

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>, call: number) {
  return new URL(fetchMock.mock.calls[call][0] as string)
}

// Text from the formatters uses non-breaking spaces. toHaveTextContent
// collapses them to plain spaces, but accessible names keep them.
const nbsp = (text: string) => text.replaceAll(' ', ' ')

afterEach(() => {
  vi.unstubAllGlobals()
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

    const rows = within(screen.getByRole('list')).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    // GAR-034: building, room, availability start and end, and duration.
    expect(rows[0]).toHaveTextContent('Dwinelle 201')
    expect(rows[0]).toHaveTextContent('Free 2:30 PM – 5:00 PM')
    expect(rows[0]).toHaveTextContent('2 h 30 min')
    expect(rows[1]).toHaveTextContent('45 min')
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
    // The search can be changed or repeated while one is loading.
    expect(screen.getByRole('button', { name: 'Find rooms' })).toBeEnabled()

    respond(jsonResponse(page([room(1)])))
    expect(
      await screen.findByRole('heading', { name: '1 room free now' }),
    ).toBeInTheDocument()
  })

  it('searches a later time', async () => {
    const user = userEvent.setup()
    const fetchMock = stubResponses(
      () => jsonResponse(page([room(1)])),
      () =>
        jsonResponse(
          page([room(1), room(2)], { date: '2026-10-06', time: '09:00' }),
        ),
    )
    render(<AvailabilitySearch termId={3} />)
    await screen.findByRole('heading', { name: '1 room free now' })

    await user.click(screen.getByRole('radio', { name: 'Later' }))
    const input = screen.getByLabelText('Date and time')
    expect((input as HTMLInputElement).value).toMatch(
      /^\d{4}-\d\d-\d\dT\d\d:[03]0$/,
    )
    await user.clear(input)
    await user.type(input, '2026-10-06T09:00')
    await user.click(screen.getByRole('button', { name: 'Find rooms' }))

    expect(
      await screen.findByRole('heading', {
        name: `2 rooms free at Tue, Oct 6, ${nbsp('9:00 AM')}`,
      }),
    ).toBeInTheDocument()
    expect(requestedUrl(fetchMock, 1).searchParams.get('at')).toBe(
      '2026-10-06T09:00',
    )
  })

  it('keeps describing the shown results while a new search loads', async () => {
    const user = userEvent.setup()
    let respond: (response: Response) => void = () => {}
    stubResponses(
      () => jsonResponse(page([room(1)])),
      () => new Promise<Response>((resolve) => (respond = resolve)),
    )
    render(<AvailabilitySearch termId={3} />)
    await screen.findByRole('heading', { name: '1 room free now' })

    await user.click(screen.getByRole('radio', { name: 'Later' }))
    await user.click(screen.getByRole('button', { name: 'Find rooms' }))

    // The dimmed results are still the "now" results, so the heading says so.
    expect(
      screen.getByRole('heading', { name: '1 room free now' }),
    ).toBeInTheDocument()

    respond(
      jsonResponse(
        page([room(1), room(2)], { date: '2026-10-06', time: '09:00' }),
      ),
    )
    expect(
      await screen.findByRole('heading', {
        name: `2 rooms free at Tue, Oct 6, ${nbsp('9:00 AM')}`,
      }),
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

    it('keeps a submitted later time', async () => {
      const user = userEvent.setup()
      const later = { date: '2026-10-06', time: '09:00' }
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)], later)),
        () => jsonResponse(page([room(1), room(2)], later)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: 'Later' }))
      const input = screen.getByLabelText('Date and time')
      await user.clear(input)
      await user.type(input, '2026-10-06T09:00')
      await user.click(screen.getByRole('button', { name: 'Find rooms' }))
      await screen.findByRole('heading', { name: /^1 room free at/ })
      await user.click(screen.getByRole('radio', { name: nbsp('30 min') }))

      await screen.findByRole('heading', { name: /^2 rooms free at/ })
      const url = requestedUrl(fetchMock, 2)
      expect(url.searchParams.get('at')).toBe('2026-10-06T09:00')
      expect(url.searchParams.get('minimum_minutes')).toBe('30')
    })

    it("doesn't apply a later time that wasn't submitted", async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: 'Later' }))
      await user.click(screen.getByRole('radio', { name: nbsp('3 h') }))

      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
      expect(requestedUrl(fetchMock, 1).searchParams.has('at')).toBe(false)
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

  describe('building filter', () => {
    const evans = (id: number) =>
      room(id, {
        building_id: 2,
        building_code: 'EVANS',
        building_name: 'Evans',
      })

    it('defaults to every building', async () => {
      const fetchMock = stubResponses(() => jsonResponse(page([room(1)])))
      render(<AvailabilitySearch termId={3} />)

      const select = await screen.findByRole('combobox', { name: 'Building' })
      expect(select).toHaveDisplayValue('All buildings')
      expect(
        within(select)
          .getAllByRole('option')
          .map((option) => option.textContent),
      ).toEqual(['All buildings', 'Dwinelle', 'Evans'])
      await screen.findByRole('heading', { name: '1 room free now' })
      expect(requestedUrl(fetchMock, 0).searchParams.has('building_id')).toBe(
        false,
      )
    })

    it('updates the results as soon as it changes, keeping the other choices', async () => {
      const user = userEvent.setup()
      const later = { date: '2026-10-06', time: '09:00' }
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1), evans(2)], later)),
        () => jsonResponse(page([evans(2)], later)),
        () => jsonResponse(page([evans(2), evans(3)], later)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: 'Later' }))
      const input = screen.getByLabelText('Date and time')
      await user.clear(input)
      await user.type(input, '2026-10-06T09:00')
      await user.click(screen.getByRole('button', { name: 'Find rooms' }))
      await screen.findByRole('heading', { name: /^2 rooms free at/ })
      await user.click(screen.getByRole('radio', { name: nbsp('2 h') }))
      await screen.findByRole('heading', { name: /^1 room free at/ })
      await user.selectOptions(
        screen.getByRole('combobox', { name: 'Building' }),
        'Evans',
      )

      expect(
        await screen.findByRole('heading', {
          name: `2 rooms free at Tue, Oct 6, ${nbsp('9:00 AM')} in Evans`,
        }),
      ).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 3)
      expect(url.searchParams.get('building_id')).toBe('2')
      expect(url.searchParams.get('at')).toBe('2026-10-06T09:00')
      expect(url.searchParams.get('minimum_minutes')).toBe('120')
    })

    it('names the building when nothing is free', async () => {
      const user = userEvent.setup()
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.selectOptions(
        await screen.findByRole('combobox', { name: 'Building' }),
        'Evans',
      )

      expect(
        await screen.findByRole('heading', {
          name: 'No rooms free now in Evans',
        }),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          /^Nothing in Evans is free for at least an hour now\./,
        ),
      ).toBeInTheDocument()
    })

    it('describes the shown results while a new building loads', async () => {
      const user = userEvent.setup()
      let respond: (response: Response) => void = () => {}
      stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
        () => new Promise<Response>((resolve) => (respond = resolve)),
      )
      render(<AvailabilitySearch termId={3} />)
      const select = await screen.findByRole('combobox', { name: 'Building' })
      await user.selectOptions(select, 'Dwinelle')
      await screen.findByRole('heading', {
        name: '1 room free now in Dwinelle',
      })

      await user.selectOptions(select, 'All buildings')
      expect(
        screen.getByRole('heading', { name: '1 room free now in Dwinelle' }),
      ).toBeInTheDocument()

      respond(jsonResponse(page([room(1), evans(2)])))
      expect(
        await screen.findByRole('heading', { name: '2 rooms free now' }),
      ).toBeInTheDocument()
    })

    it('keeps the building when showing more and trying again', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse({}, 503),
        () => jsonResponse(page([evans(2), evans(3)], { total: 3 })),
        () => jsonResponse(page([evans(4)], { total: 3, offset: 2 })),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.selectOptions(
        await screen.findByRole('combobox', { name: 'Building' }),
        'Evans',
      )
      await screen.findByRole('alert')
      await user.click(screen.getByRole('button', { name: 'Try again' }))
      await screen.findByText('Showing 2 of 3')
      await user.click(screen.getByRole('button', { name: 'Show more' }))
      await screen.findByText('Evans 204')

      expect(requestedUrl(fetchMock, 2).searchParams.get('building_id')).toBe(
        '2',
      )
      expect(requestedUrl(fetchMock, 3).searchParams.get('building_id')).toBe(
        '2',
      )
    })

    it.each([
      ['an error', () => jsonResponse({}, 503)],
      [
        'a failed connection',
        () => {
          throw new TypeError('Failed to fetch')
        },
      ],
    ])(
      'is left out when the buildings fail to load with %s',
      async (_, buildings) => {
        const fetchMock = stubApi({
          buildings,
          availability: [() => jsonResponse(page([room(1)]))],
        })
        render(<AvailabilitySearch termId={3} />)

        await screen.findByRole('heading', { name: '1 room free now' })
        await waitFor(() =>
          expect(fetch).toHaveBeenCalledWith(
            expect.stringMatching(/\/buildings$/),
            expect.anything(),
          ),
        )
        expect(
          screen.queryByRole('combobox', { name: 'Building' }),
        ).not.toBeInTheDocument()
        expect(screen.queryByRole('alert')).not.toBeInTheDocument()
        expect(requestedUrl(fetchMock, 0).searchParams.has('building_id')).toBe(
          false,
        )
      },
    )
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

    it('applies together with the other filters and a submitted time', async () => {
      const user = userEvent.setup()
      const later = { date: '2026-10-06', time: '09:00' }
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)], later)),
        () => jsonResponse(page([room(1)], later)),
        () => jsonResponse(page([room(1)], later)),
        () => jsonResponse(page([], later)),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.click(screen.getByRole('radio', { name: 'Later' }))
      const input = screen.getByLabelText('Date and time')
      await user.clear(input)
      await user.type(input, '2026-10-06T09:00')
      await user.click(screen.getByRole('button', { name: 'Find rooms' }))
      await screen.findByRole('heading', { name: /^1 room free at/ })
      await user.click(screen.getByRole('radio', { name: nbsp('2 h') }))
      await user.selectOptions(
        await screen.findByRole('combobox', { name: 'Building' }),
        'Evans',
      )
      await screen.findByRole('heading', { name: /in Evans$/ })
      await user.type(searchField(), '101')

      expect(
        await screen.findByRole('heading', {
          name: `No rooms free at Tue, Oct 6, ${nbsp('9:00 AM')} in Evans matching “101”`,
        }),
      ).toBeInTheDocument()
      const url = requestedUrl(fetchMock, 4)
      expect(url.searchParams.get('at')).toBe('2026-10-06T09:00')
      expect(url.searchParams.get('minimum_minutes')).toBe('120')
      expect(url.searchParams.get('building_id')).toBe('2')
      expect(url.searchParams.get('room')).toBe('101')
    })

    it('searches right away on Enter', async () => {
      const user = userEvent.setup()
      const fetchMock = stubResponses(
        () => jsonResponse(page([room(1)])),
        () => jsonResponse(page([room(1)])),
      )
      render(<AvailabilitySearch termId={3} />)
      await screen.findByRole('heading', { name: '1 room free now' })

      await user.type(searchField(), '  Evans {Enter}')

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
          screen.getByRole('heading').closest('[aria-busy]'),
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
      await screen.findByText('Dwinelle 203')

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

    await screen.findByText('Dwinelle 203')
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
})
