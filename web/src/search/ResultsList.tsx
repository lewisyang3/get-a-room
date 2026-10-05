import type {
  AvailabilityPage,
  AvailabilityResult,
  SearchWhen,
} from '../api/availability'
import type { Building } from '../api/buildings'
import type { ApiError } from '../api/http'
import {
  formatClockTime,
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

// The name of the building the results are for, or null for every building.
function buildingName(
  buildings: Building[] | null,
  buildingId: number | null,
): string | null {
  if (buildingId === null) return null
  const building = buildings?.find((b) => b.building_id === buildingId)
  return building?.building_name ?? null
}

function ResultRow({ result }: { result: AvailabilityResult }) {
  return (
    <li className={styles.row}>
      <div className={styles.rowMain}>
        <span className={styles.roomName}>
          {result.building_name} {result.room_number}
        </span>
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
  page,
}: {
  when: SearchWhen
  minimumMinutes: number
  buildingName: string | null
  page: AvailabilityPage
}) {
  const moment = formatSearchMoment(when, page)
  const minimum = formatMinimumDuration(minimumMinutes)
  const place = buildingName ? ` in ${buildingName}` : ''
  if (page.total === 0) {
    return (
      <>
        <h2 className={styles.summaryTitle}>
          No rooms free {moment}
          {place}
        </h2>
        <p className={styles.secondary}>
          Nothing{place} is free for at least {minimum} {moment}. Availability
          covers 7&nbsp;a.m. to 10&nbsp;p.m. on days during the term.
        </p>
      </>
    )
  }
  return (
    <>
      <h2 className={styles.summaryTitle}>
        {roomCount(page.total)} free {moment}
        {place}
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
          page={page}
        />
      </div>
      {results.length > 0 && (
        <ul className={styles.list}>
          {results.map((result) => (
            <ResultRow key={result.room_id} result={result} />
          ))}
        </ul>
      )}
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
