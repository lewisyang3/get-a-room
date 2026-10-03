import { useEffect } from 'react'
import { DEFAULT_MINIMUM_MINUTES } from '../api/availability'
import { termId as configuredTermId } from '../config'
import ResultsList from './ResultsList'
import SearchForm from './SearchForm'
import { useAvailability } from './useAvailability'
import styles from './AvailabilitySearch.module.css'

function Search({ termId }: { termId: number }) {
  const availability = useAvailability(termId)
  const { search } = availability

  // Most visits ask "what's free now?", so answer it without a tap.
  useEffect(() => {
    void search({
      when: { kind: 'now' },
      minimumMinutes: DEFAULT_MINIMUM_MINUTES,
    })
  }, [search])

  return (
    <section className={styles.search} aria-label="Find a room">
      <SearchForm
        onSearch={(when) =>
          void search({ when, minimumMinutes: DEFAULT_MINIMUM_MINUTES })
        }
      />
      <ResultsList
        {...availability}
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
