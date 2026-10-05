import { useEffect, useEffectEvent, useState } from 'react'
import { DEFAULT_MINIMUM_MINUTES, type SearchWhen } from '../api/availability'
import { termId as configuredTermId } from '../config'
import ResultsList from './ResultsList'
import { normalizeSearchText } from './roomSearch'
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

// How long typing pauses before the search text applies.
const TEXT_DEBOUNCE_MS = 300

function Search({ termId }: { termId: number }) {
  const availability = useAvailability(termId)
  const { search, query } = availability
  const buildings = useBuildings()
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  // The search field as typed, which applies once typing pauses.
  const [draftText, setDraftText] = useState('')

  // Re-runs the latest search's time with the new filters. A time typed into
  // Later but not yet submitted waits for Find rooms.
  function changeFilters(change: Partial<Filters>) {
    const next = { ...filters, ...change }
    setFilters(next)
    void search({ when: query?.when ?? { kind: 'now' }, ...next })
  }

  // Skips text that only differs in whitespace, or was already applied by
  // submitting the form.
  const applyText = useEffectEvent((text: string) => {
    if (text !== filters.text) changeFilters({ text })
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
    const next = { ...filters, text: normalizeSearchText(draftText) }
    setFilters(next)
    void search({ when, ...next })
  }

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
