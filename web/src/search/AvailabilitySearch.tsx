import { useEffect, useEffectEvent, useRef, useState } from 'react'
import {
  DEFAULT_MINIMUM_MINUTES,
  type Point,
  type SearchWhen,
} from '../api/availability'
import { termId as configuredTermId } from '../config'
import ResultsList from './ResultsList'
import { normalizeSearchText } from './roomSearch'
import SearchForm, { type SortOrder } from './SearchForm'
import { useAvailability, type SearchQuery } from './useAvailability'
import { useBuildings } from './useBuildings'
import { useLocation } from './useLocation'
import styles from './AvailabilitySearch.module.css'

type Filters = Omit<SearchQuery, 'when'>

const DEFAULT_FILTERS: Filters = {
  minimumMinutes: DEFAULT_MINIMUM_MINUTES,
  buildingId: null,
  text: '',
  near: null,
}

// How long typing pauses before the search text applies.
const TEXT_DEBOUNCE_MS = 300

function samePoint(a: Point | null, b: Point | null): boolean {
  return a?.latitude === b?.latitude && a?.longitude === b?.longitude
}

const LOCATION_MESSAGES = {
  locating: 'Finding your location…',
  failed: "Couldn't get your location, so rooms are sorted by building.",
}

function Search({ termId }: { termId: number }) {
  const availability = useAvailability(termId)
  const { search } = availability
  const buildings = useBuildings()
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  // The latest search's time and filters. Refs, so a search started after a
  // wait (typing, finding the location) builds on the latest ones.
  const whenRef = useRef<SearchWhen>({ kind: 'now' })
  const filtersRef = useRef(DEFAULT_FILTERS)
  // The search field as typed, which applies once typing pauses.
  const [draftText, setDraftText] = useState('')
  const location = useLocation()
  // The Sort control's choice. Nearest shows as chosen while the location
  // is found, before the search can sort by it.
  const [sort, setSort] = useState<SortOrder>('building')
  const sortRef = useRef(sort)
  // Sorting by distance only helps when some building's location is known.
  const canSortByDistance =
    location.supported &&
    (buildings?.some(
      (building) => building.latitude !== null && building.longitude !== null,
    ) ??
      false)

  function runSearch(when: SearchWhen, next: Filters) {
    whenRef.current = when
    filtersRef.current = next
    setFilters(next)
    void search({ when, ...next })
  }

  // Re-runs the latest search's time with the new filters. A time typed into
  // Later but not yet submitted waits for Find rooms.
  function changeFilters(change: Partial<Filters>) {
    runSearch(whenRef.current, { ...filtersRef.current, ...change })
  }

  // Skips text that only differs in whitespace, or was already applied by
  // submitting the form.
  const applyText = useEffectEvent((text: string) => {
    if (text !== filtersRef.current.text) changeFilters({ text })
  })

  useEffect(() => {
    const timer = setTimeout(
      () => applyText(normalizeSearchText(draftText)),
      TEXT_DEBOUNCE_MS,
    )
    return () => clearTimeout(timer)
  }, [draftText])

  // Submitting applies the search text right away, without waiting.
  function submit(when: SearchWhen) {
    runSearch(when, {
      ...filtersRef.current,
      text: normalizeSearchText(draftText),
    })
  }

  // The location is asked for only when Nearest is chosen. If it can't be
  // found, the sort goes back to Building.
  function changeSort(next: SortOrder) {
    sortRef.current = next
    setSort(next)
    if (next === 'building') {
      if (filtersRef.current.near !== null) changeFilters({ near: null })
      return
    }
    void location.locate().then((near) => {
      // Building was chosen again while the location was found.
      if (sortRef.current !== 'nearest') return
      if (near === null) {
        sortRef.current = 'building'
        setSort('building')
      } else if (!samePoint(near, filtersRef.current.near)) {
        changeFilters({ near })
      }
    })
  }

  const locationMessage =
    location.status === 'locating' && sort === 'nearest'
      ? LOCATION_MESSAGES.locating
      : location.status === 'failed' && sort === 'building'
        ? LOCATION_MESSAGES.failed
        : ''

  // Most visits ask "what's free now?", so answer it without a tap.
  useEffect(() => {
    void search({ when: { kind: 'now' }, ...DEFAULT_FILTERS })
  }, [search])

  return (
    <section className={styles.search} aria-label="Find a room">
      <SearchForm
        onSearch={submit}
        minimumMinutes={filters.minimumMinutes}
        onMinimumMinutesChange={(minimumMinutes) =>
          changeFilters({ minimumMinutes })
        }
        buildings={buildings}
        buildingId={filters.buildingId}
        onBuildingChange={(buildingId) => changeFilters({ buildingId })}
        text={draftText}
        onTextChange={setDraftText}
        sort={canSortByDistance ? sort : null}
        onSortChange={changeSort}
        locationMessage={locationMessage}
      />
      <ResultsList
        {...availability}
        buildings={buildings}
        onRetry={availability.retry}
        onLoadMore={() => void availability.loadMore()}
      />
    </section>
  )
}

/** The time search and its results. `termId` defaults to VITE_TERM_ID. */
function AvailabilitySearch({
  termId = configuredTermId,
}: {
  termId?: number | null
}) {
  if (termId === null) {
    return (
      <p className={styles.message} role="status">
        Search isn't set up yet: VITE_TERM_ID needs to name the term to search.
      </p>
    )
  }
  return <Search termId={termId} />
}

export default AvailabilitySearch
