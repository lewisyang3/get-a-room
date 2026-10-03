import { StrictMode } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AvailabilityPage, AvailabilityResult } from '../api/availability'
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

/** Stubs fetch to answer each request in turn with the given responses. */
function stubResponses(...responses: (() => Response | Promise<Response>)[]) {
  const fetchMock = vi.fn(async () => {
    const next = responses.shift()
    if (!next) throw new Error('Unexpected request')
    return next()
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
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
    const fetchMock = stubResponses()
    render(<AvailabilitySearch termId={null} />)

    expect(screen.getByRole('status')).toHaveTextContent(
      "Search isn't set up yet",
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
