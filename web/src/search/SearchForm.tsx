import { useId, type FormEvent } from 'react'
import { MINIMUM_MINUTES_OPTIONS } from '../api/availability'
import { formatDuration, formatMinimumDuration } from '../format'
import styles from './AvailabilitySearch.module.css'
import SegmentedControl, { type SegmentedOption } from './SegmentedControl'

type Props = {
  onSearch: () => void
  minimumMinutes: number
  onMinimumMinutesChange: (minutes: number) => void
  /** The room or building search, as typed. */
  text: string
  onTextChange: (text: string) => void
}

// Screen readers say "2 hours" for the short "2h".
const DURATION_OPTIONS: SegmentedOption<number>[] = MINIMUM_MINUTES_OPTIONS.map(
  (minutes) => ({
    value: minutes,
    label: formatDuration(minutes),
    accessibleLabel: formatMinimumDuration(minutes),
  }),
)

function SearchForm({
  onSearch,
  minimumMinutes,
  onMinimumMinutesChange,
  text,
  onTextChange,
}: Props) {
  const id = useId()
  const textId = `${id}-text`

  // Enter in the search field searches right away.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSearch()
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
    </form>
  )
}

export default SearchForm
