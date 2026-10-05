import { useEffect, useState } from 'react'
import { DEFAULT_MINIMUM_MINUTES } from '../api/availability'
import { termId as configuredTermId } from '../config'
import ResultsList from './ResultsList'
import SearchForm from './SearchForm'
import { useAvailability, type SearchQuery } from './useAvailability'
import { useBuildings } from './useBuildings'
import styles from './AvailabilitySearch.module.css'

type Filters = Omit<SearchQuery, 'when'>

const DEFAULT_FILTERS: Filters = {
  minimumMinutes: DEFAULT_MINIMUM_MINUTES,
  buildingId: null,
  text: '',
}

function Search({ termId }: { termId: number }) {
  const availability = useAvailability(termId)
  const { search, query } = availability
  const buildings = useBuildings()
  const [filters, setFilters] = useState(DEFAULT_FILTERS)

  // Re-runs the latest search's time with the new filters. A time typed into
  // Later but not yet submitted waits for Find rooms.
  function changeFilters(change: Partial<Filters>) {
    const next = { ...filters, ...change }
    setFilters(next)
    void search({ when: query?.when ?? { kind: 'now' }, ...next })
  }

  // Most visits ask "what's free now?", so answer it without a tap.
  useEffect(() => {
    void search({ when: { kind: 'now' }, ...DEFAULT_FILTERS })
  }, [search])

  return (
    <section className={styles.search} aria-label="Find a room">
      <SearchForm
        onSearch={(when) => void search({ when, ...filters })}
        minimumMinutes={filters.minimumMinutes}
        onMinimumMinutesChange={(minimumMinutes) =>
          changeFilters({ minimumMinutes })
        }
        buildings={buildings}
        buildingId={filters.buildingId}
        onBuildingChange={(buildingId) => changeFilters({ buildingId })}
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
