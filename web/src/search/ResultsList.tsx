import { useId } from 'react'
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
import type { AvailabilityState } from './useAvailability'
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
            aria-label={`Directions to ${name}`}
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
  when,
  minimumMinutes,
  buildingName,
  text,
  page,
}: {
  when: SearchWhen
  minimumMinutes: number
  buildingName: string | null
  text: string
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
        <h2 className={styles.summaryTitle}>
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
      <h2 className={styles.summaryTitle}>
        {roomCount(page.total)} free {moment}
        {place}
        {matching}
      </h2>
      <p className={styles.secondary}>For at least {minimum}</p>
    </>
  )
}

function ResultsList({
  status,
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
  if (status === 'idle') return null

  if (status === 'error' && error) {
    return (
      <div className={styles.message} role="alert">
        <p>{ERROR_MESSAGES[error.kind]}</p>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onRetry}
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
      className={loading ? `${styles.results} ${styles.stale}` : styles.results}
      aria-busy={loading}
    >
      <div className={styles.summary} aria-live="polite">
        <Summary
          when={resultsQuery.when}
          minimumMinutes={resultsQuery.minimumMinutes}
          buildingName={buildingName(buildings, resultsQuery.buildingId)}
          text={resultsQuery.text}
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
            type="button"
            className={styles.secondaryButton}
            onClick={onLoadMore}
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
