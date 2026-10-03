import { useId, useState, type FormEvent } from 'react'
import type { SearchWhen } from '../api/availability'
import { nextHalfHourInPacific } from '../format'
import styles from './AvailabilitySearch.module.css'

type Props = {
  onSearch: (when: SearchWhen) => void
}

function SearchForm({ onSearch }: Props) {
  const [mode, setMode] = useState<'now' | 'later'>('now')
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
      <fieldset className={styles.when} aria-describedby={hintId}>
        <legend className={styles.legend}>When</legend>
        <div className={styles.segmented}>
          <label className={styles.segment}>
            <input
              type="radio"
              name={`${id}-mode`}
              value="now"
              checked={mode === 'now'}
              onChange={() => setMode('now')}
            />
            Now
          </label>
          <label className={styles.segment}>
            <input
              type="radio"
              name={`${id}-mode`}
              value="later"
              checked={mode === 'later'}
              onChange={() => setMode('later')}
            />
            Later
          </label>
        </div>
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
      <p id={hintId} className={styles.hint}>
        Pacific time · 7&nbsp;a.m. to 10&nbsp;p.m.
      </p>
    </form>
  )
}

export default SearchForm
