import { useId, type FormEvent } from 'react'
import { MINIMUM_MINUTES_OPTIONS, type SearchWhen } from '../api/availability'
import { formatDuration } from '../format'
import styles from './AvailabilitySearch.module.css'
import SegmentedControl, { type SegmentedOption } from './SegmentedControl'

type Props = {
  onSearch: (when: SearchWhen) => void
  minimumMinutes: number
  onMinimumMinutesChange: (minutes: number) => void
  /** The room or building search, as typed. */
  text: string
  onTextChange: (text: string) => void
  /** How results are sorted, or null to leave the Sort control out. */
  sort: SortOrder | null
  onSortChange: (sort: SortOrder) => void
  /** Progress or trouble finding the device's location, or ''. */
  locationMessage: string
}

export type SortOrder = 'building' | 'nearest'

const SORT_OPTIONS: SegmentedOption<SortOrder>[] = [
  { value: 'building', label: 'Building' },
  { value: 'nearest', label: 'Nearest' },
]

const DURATION_OPTIONS: SegmentedOption<number>[] = MINIMUM_MINUTES_OPTIONS.map(
  (minutes) => ({ value: minutes, label: formatDuration(minutes) }),
)

function SearchForm({
  onSearch,
  minimumMinutes,
  onMinimumMinutesChange,
  text,
  onTextChange,
  sort,
  onSortChange,
  locationMessage,
}: Props) {
  const id = useId()
  const textId = `${id}-text`

  // Enter in the search field searches right away.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSearch({ kind: 'now' })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Search">
      {/* A filter refines the results on screen, so it applies right away. */}
      <fieldset className={`${styles.field} ${styles.fullRow}`}>
        <legend className={styles.legend}>Free for at least</legend>
        <SegmentedControl
          name={`${id}-minimum`}
          options={DURATION_OPTIONS}
          value={minimumMinutes}
          onChange={onMinimumMinutesChange}
        />
      </fieldset>
      <div className={`${styles.field} ${styles.fullRow}`}>
        <label htmlFor={textId} className={styles.legend}>
          Room or building
        </label>
        <input
          id={textId}
          className={styles.searchInput}
          type="search"
          placeholder="e.g. Dwinelle 242"
          enterKeyHint="search"
          autoComplete="off"
          spellCheck={false}
          value={text}
          onChange={(event) => onTextChange(event.target.value)}
        />
      </div>
      {sort !== null && (
        <fieldset className={`${styles.field} ${styles.fullRow}`}>
          <legend className={styles.legend}>Sort</legend>
          <SegmentedControl
            name={`${id}-sort`}
            options={SORT_OPTIONS}
            value={sort}
            onChange={onSortChange}
          />
          {/* Always rendered, so screen readers announce changes to it. */}
          <span role="status" className={styles.secondary}>
            {locationMessage}
          </span>
        </fieldset>
      )}
    </form>
  )
}

export default SearchForm
