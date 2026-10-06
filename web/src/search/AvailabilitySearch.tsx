import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  DEFAULT_MINIMUM_MINUTES,
  type Point,
  type SearchWhen,
} from '../api/availability'
import {
  termId as configuredTermId,
  mapboxToken as configuredMapboxToken,
} from '../config'
import { useMediaQuery } from '../useMediaQuery'
import ResultsList from './ResultsList'
import { normalizeSearchText } from './roomSearch'
import SearchForm, { type SortOrder } from './SearchForm'
import SegmentedControl, { type SegmentedOption } from './SegmentedControl'
import { useAvailability, type SearchQuery } from './useAvailability'
import { useBuildingAvailability } from './useBuildingAvailability'
import { useBuildings } from './useBuildings'
import { useLocation } from './useLocation'
import styles from './AvailabilitySearch.module.css'

// Mapbox GL is large, so it loads only when the map is shown.
const CampusMap = lazy(() => import('./CampusMap'))

// Wide enough for the results and the map side by side.
const SIDE_BY_SIDE = '(min-width: 64rem)'

type View = 'list' | 'map'

const VIEW_OPTIONS: SegmentedOption<View>[] = [
  { value: 'list', label: 'List' },
  { value: 'map', label: 'Map' },
]

/** Leaves the map out if its code fails to load or it fails to render, so
 * the list still works. */
class MapBoundary extends Component<
  { onError: () => void; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch() {
    this.props.onError()
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

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

function Search({
  termId,
  mapboxToken,
}: {
  termId: number
  mapboxToken: string | null
}) {
  const availability = useAvailability(termId)
  const { search } = availability
  const buildings = useBuildings()
  const id = useId()
  const sideBySide = useMediaQuery(SIDE_BY_SIDE)
  // On narrow screens, the list or the map.
  const [view, setView] = useState<View>('list')
  const [mapFailed, setMapFailed] = useState(false)
  // The map needs a token, and at least one building to put on it.
  const showMap =
    mapboxToken !== null &&
    !mapFailed &&
    (buildings?.some(
      (building) => building.latitude !== null && building.longitude !== null,
    ) ??
      false)
  // Counts are only fetched for the map.
  const counts = useBuildingAvailability(
    termId,
    showMap ? availability.resultsQuery : null,
    availability.page,
  )
  const mapShown = showMap && (sideBySide || view === 'map')
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

  // Re-runs the latest search's time with the new filters.
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

  // Choosing a building on the map filters the results to it. On a narrow
  // screen it also goes back to the list, to show that building's rooms.
  function selectOnMap(buildingId: number | null) {
    changeFilters({ buildingId })
    if (!sideBySide && buildingId !== null) setView('list')
  }

  const map = mapShown && mapboxToken && buildings && (
    <div className={styles.mapPane}>
      <MapBoundary onError={() => setMapFailed(true)}>
        <Suspense fallback={null}>
          <CampusMap
            token={mapboxToken}
            buildings={buildings}
            counts={counts}
            selectedBuildingId={filters.buildingId}
            onSelect={selectOnMap}
            onUnavailable={() => setMapFailed(true)}
          />
        </Suspense>
      </MapBoundary>
    </div>
  )

  return (
    <section
      className={styles.search}
      // The page widens for the map, and LandingPage styles that.
      data-layout={showMap && sideBySide ? 'side-by-side' : undefined}
      aria-label="Find a room"
    >
      <div className={styles.searchColumn}>
        <SearchForm
          onSearch={submit}
          minimumMinutes={filters.minimumMinutes}
          onMinimumMinutesChange={(minimumMinutes) =>
            changeFilters({ minimumMinutes })
          }
          text={draftText}
          onTextChange={setDraftText}
          sort={canSortByDistance ? sort : null}
          onSortChange={changeSort}
          locationMessage={locationMessage}
        />
        {showMap && !sideBySide && (
          <fieldset className={styles.field}>
            <legend className={styles.legend}>Show</legend>
            <SegmentedControl
              name={`${id}-view`}
              options={VIEW_OPTIONS}
              value={view}
              onChange={setView}
            />
          </fieldset>
        )}
        {/* Hidden rather than removed in Map view, so it keeps its place. */}
        <div hidden={mapShown && !sideBySide}>
          <ResultsList
            {...availability}
            buildings={buildings}
            onRetry={availability.retry}
            onLoadMore={() => void availability.loadMore()}
            onShowAllBuildings={() => changeFilters({ buildingId: null })}
          />
        </div>
        {!sideBySide && map}
      </div>
      {sideBySide && map}
    </section>
  )
}

/** The time search and its results. `termId` defaults to VITE_TERM_ID, and
 * `mapboxToken` to VITE_MAPBOX_TOKEN; without a token there's no map. */
function AvailabilitySearch({
  termId = configuredTermId,
  mapboxToken = configuredMapboxToken,
}: {
  termId?: number | null
  mapboxToken?: string | null
}) {
  if (termId === null) {
    return (
      <p className={styles.message} role="status">
        Search isn't set up yet: VITE_TERM_ID needs to name the term to search.
      </p>
    )
  }
  return <Search termId={termId} mapboxToken={mapboxToken} />
}

export default AvailabilitySearch
