import { useId, useState, type FormEvent } from 'react'
import { MINIMUM_MINUTES_OPTIONS, type SearchWhen } from '../api/availability'
import { formatDuration, nextHalfHourInPacific } from '../format'
import styles from './AvailabilitySearch.module.css'
import SegmentedControl, { type SegmentedOption } from './SegmentedControl'

type Props = {
  onSearch: (when: SearchWhen) => void
  minimumMinutes: number
  onMinimumMinutesChange: (minutes: number) => void
}

type Mode = 'now' | 'later'

const MODE_OPTIONS: SegmentedOption<Mode>[] = [
  { value: 'now', label: 'Now' },
  { value: 'later', label: 'Later' },
]

const DURATION_OPTIONS: SegmentedOption<number>[] = MINIMUM_MINUTES_OPTIONS.map(
  (minutes) => ({ value: minutes, label: formatDuration(minutes) }),
)

function SearchForm({
  onSearch,
  minimumMinutes,
  onMinimumMinutesChange,
}: Props) {
  const [mode, setMode] = useState<Mode>('now')
  const [at, setAt] = useState(() => nextHalfHourInPacific(new Date()))
  const id = useId()
  const hintId = `${id}-hint`
  const atId = `${id}-at`

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSearch(mode === 'now' ? { kind: 'now' } : { kind: 'at', at })
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Search">
      <fieldset className={styles.field} aria-describedby={hintId}>
        <legend className={styles.legend}>When</legend>
        <SegmentedControl
          name={`${id}-mode`}
          options={MODE_OPTIONS}
          value={mode}
          onChange={setMode}
        />
        {mode === 'later' && (
          <>
            <label htmlFor={atId} className={styles.visuallyHidden}>
              Date and time
            </label>
            <input
              id={atId}
              className={styles.dateTime}
              type="datetime-local"
              required
              value={at}
              onChange={(event) => setAt(event.target.value)}
            />
          </>
        )}
      </fieldset>
      <button type="submit" className={styles.primaryButton}>
        Find rooms
      </button>
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
      <p id={hintId} className={styles.hint}>
        Pacific time · 7&nbsp;a.m. to 10&nbsp;p.m.
      </p>
    </form>
  )
}

export default SearchForm
