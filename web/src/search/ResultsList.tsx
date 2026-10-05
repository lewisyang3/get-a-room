import { useEffect, useId, useRef, type Ref } from 'react'
import type {
  AvailabilityPage,
  AvailabilityResult,
  SearchWhen,
} from '../api/availability'
import type { Building } from '../api/buildings'
import type { ApiError } from '../api/http'
import {
  formatClockTime,
  formatDistance,
  formatDuration,
  formatMinimumDuration,
  formatSearchMoment,
} from '../format'
import type { AvailabilityState, SearchQuery } from './useAvailability'
import styles from './AvailabilitySearch.module.css'

type Props = AvailabilityState & {
  buildings: Building[] | null
  onRetry: () => void
  onLoadMore: () => void
}

const ERROR_MESSAGES: Record<ApiError['kind'], string> = {
  network: "Couldn't reach Get a Room. Check your connection and try again.",
  'not-found': "This term isn't available.",
  invalid: 'Something went wrong with that search.',
  server: 'Something went wrong with that search.',
}

function roomCount(count: number): string {
  return `${count} ${count === 1 ? 'room' : 'rooms'}`
}

function findBuilding(
  buildings: Building[] | null,
  buildingId: number,
): Building | undefined {
  return buildings?.find((building) => building.building_id === buildingId)
}

// The name of the building the results are for, or null for every building.
function buildingName(
  buildings: Building[] | null,
  buildingId: number | null,
): string | null {
  if (buildingId === null) return null
  return findBuilding(buildings, buildingId)?.building_name ?? null
}

type BuildingGroup = { buildingId: number; results: AvailabilityResult[] }

/** Groups consecutive rooms in the same building. The API lists each
 * building's rooms together, in either order, so a building split across
 * pages still forms one group. */
function groupByBuilding(results: AvailabilityResult[]): BuildingGroup[] {
  const groups: BuildingGroup[] = []
  for (const result of results) {
    const last = groups.at(-1)
    if (last?.buildingId === result.building_id) last.results.push(result)
    else groups.push({ buildingId: result.building_id, results: [result] })
  }
  return groups
}

function directionsUrl({ latitude, longitude }: Building): string | null {
  if (latitude === null || longitude === null) return null
  const params = new URLSearchParams({
    api: '1',
    destination: `${latitude},${longitude}`,
    travelmode: 'walking',
  })
  return `https://www.google.com/maps/dir/?${params}`
}

function BuildingGroupView({
  id,
  group,
  building,
  sortedByDistance,
}: {
  id: string
  group: BuildingGroup
  building: Building | undefined
  sortedByDistance: boolean
}) {
  const [first] = group.results
  const name = first.building_name
  const distance =
    first.distance_meters !== null
      ? formatDistance(first.distance_meters)
      : sortedByDistance
        ? 'Location unknown'
        : null
  const directions = building ? directionsUrl(building) : null
  return (
    <section className={styles.group} aria-labelledby={id}>
      <div className={styles.groupHeader}>
        <h3 id={id} className={styles.groupTitle}>
          {name}
        </h3>
        {distance && <span className={styles.secondary}>{distance}</span>}
        {directions && (
          <a
            className={styles.groupLink}
            href={directions}
            target="_blank"
            rel="noopener noreferrer"
            // Says it opens a new tab, which the visible text doesn't.
            aria-label={`Directions to ${name} (opens in a new tab)`}
          >
            Directions
          </a>
        )}
      </div>
      <ul className={styles.list}>
        {group.results.map((result) => (
          <ResultRow key={result.room_id} result={result} />
        ))}
      </ul>
    </section>
  )
}

function ResultRow({ result }: { result: AvailabilityResult }) {
  return (
    <li className={styles.row}>
      <div className={styles.rowMain}>
        <span className={styles.roomName}>Room {result.room_number}</span>
        <span className={styles.secondary}>
          Free{' '}
          <time dateTime={result.available_from}>
            {formatClockTime(result.available_from)}
          </time>{' '}
          –{' '}
          <time dateTime={result.available_until}>
            {formatClockTime(result.available_until)}
          </time>
        </span>
      </div>
      <span className={styles.duration}>
        {formatDuration(result.available_minutes)}
      </span>
    </li>
  )
}

function Summary({
  titleRef,
  when,
  minimumMinutes,
  buildingName,
  text,
  nearestFirst,
  page,
}: {
  titleRef: Ref<HTMLHeadingElement>
  when: SearchWhen
  minimumMinutes: number
  buildingName: string | null
  text: string
  nearestFirst: boolean
  page: AvailabilityPage
}) {
  const moment = formatSearchMoment(when, page)
  const minimum = formatMinimumDuration(minimumMinutes)
  const place = buildingName ? ` in ${buildingName}` : ''
  const quoted = `“${text}”`
  const matching = text ? ` matching ${quoted}` : ''
  if (page.total === 0) {
    return (
      <>
        <h2 ref={titleRef} className={styles.summaryTitle} tabIndex={-1}>
          No rooms free {moment}
          {place}
          {matching}
        </h2>
        {text ? (
          <p className={styles.secondary}>
            No free room{place} matches {quoted} for at least {minimum} {moment}
            . Check the room number, or try part of the building name.
          </p>
        ) : (
          <p className={styles.secondary}>
            Nothing{place} is free for at least {minimum} {moment}. Availability
            covers 7&nbsp;a.m. to 10&nbsp;p.m. on days during the term.
          </p>
        )}
      </>
    )
  }
  return (
    <>
      <h2 ref={titleRef} className={styles.summaryTitle} tabIndex={-1}>
        {roomCount(page.total)} free {moment}
        {place}
        {matching}
      </h2>
      <p className={styles.secondary}>
        For at least {minimum}
        {nearestFirst && ' · Nearest first'}
      </p>
    </>
  )
}

// Where focus goes once a Show more or Try again finishes: the first new
// row, or the results of the retried search.
type PendingFocus =
  | { kind: 'row'; index: number }
  | { kind: 'results'; query: SearchQuery | null }

function ResultsList({
  status,
  query,
  resultsQuery,
  buildings,
  page,
  results,
  error,
  loadingMore,
  loadMoreError,
  onRetry,
  onLoadMore,
}: Props) {
  const id = useId()
  const resultsRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const retryRef = useRef<HTMLButtonElement>(null)
  const moreRef = useRef<HTMLButtonElement>(null)
  // Show more is disabled while it loads, and Try again goes away, so
  // browsers drop focus to the page. Moving it on afterwards keeps keyboard
  // and screen reader users in their place.
  const pendingFocus = useRef<PendingFocus | null>(null)

  useEffect(() => {
    const target = pendingFocus.current
    if (target === null) return
    if (target.kind === 'results') {
      // A new search replaced the retry, so focus stays where the user is.
      if (query !== target.query) pendingFocus.current = null
      else if (status === 'success') titleRef.current?.focus()
      // Failed again, so the new Try again button takes focus instead.
      else if (status === 'error') retryRef.current?.focus()
      else return
    } else {
      // A new search replaced the rooms being added to.
      if (status === 'loading') pendingFocus.current = null
      if (status !== 'success') return
      if (loadMoreError) {
        // Couldn't load more: back to the button, now Try again.
        moreRef.current?.focus()
      } else {
        const row = resultsRef.current?.querySelectorAll('li')[target.index]
        if (!row) return
        row.tabIndex = -1
        row.focus()
      }
    }
    pendingFocus.current = null
  }, [status, query, results, loadMoreError])

  function retry() {
    // The same query is searched again; a new search would be a new object.
    pendingFocus.current = { kind: 'results', query }
    onRetry()
  }

  function loadMore() {
    pendingFocus.current = { kind: 'row', index: results.length }
    onLoadMore()
  }

  if (status === 'idle') return null

  if (status === 'error' && error) {
    return (
      <div className={styles.message} role="alert">
        <p>{ERROR_MESSAGES[error.kind]}</p>
        <button
          type="button"
          ref={retryRef}
          className={styles.secondaryButton}
          onClick={retry}
        >
          Try again
        </button>
      </div>
    )
  }

  if (!page || !resultsQuery) {
    return (
      <p className={styles.message} role="status">
        Finding rooms…
      </p>
    )
  }

  const loading = status === 'loading'
  const remaining = page.total - results.length

  return (
    <div
      ref={resultsRef}
      className={loading ? `${styles.results} ${styles.stale}` : styles.results}
      aria-busy={loading}
    >
      <div className={styles.summary} aria-live="polite">
        <Summary
          titleRef={titleRef}
          when={resultsQuery.when}
          minimumMinutes={resultsQuery.minimumMinutes}
          buildingName={buildingName(buildings, resultsQuery.buildingId)}
          text={resultsQuery.text}
          nearestFirst={resultsQuery.near !== null}
          page={page}
        />
      </div>
      {groupByBuilding(results).map((group, index) => (
        <BuildingGroupView
          // A building can't appear twice, but the index keeps keys unique
          // even if the data changed between pages.
          key={`${group.buildingId}-${index}`}
          id={`${id}-group-${index}`}
          group={group}
          building={findBuilding(buildings, group.buildingId)}
          sortedByDistance={resultsQuery.near !== null}
        />
      ))}
      {remaining > 0 && (
        <div className={styles.more}>
          <p className={styles.secondary}>
            Showing {results.length} of {page.total}
          </p>
          {loadMoreError && (
            <p className={styles.secondary} role="alert">
              Couldn't load more rooms.
            </p>
          )}
          <button
            ref={moreRef}
            type="button"
            className={styles.secondaryButton}
            onClick={loadMore}
            disabled={loadingMore || loading}
          >
            {loadingMore
              ? 'Loading…'
              : loadMoreError
                ? 'Try again'
                : 'Show more'}
          </button>
        </div>
      )}
    </div>
  )
}

export default ResultsList
