import AvailabilitySearch from '../search/AvailabilitySearch'
import styles from './LandingPage.module.css'

function LandingPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <p className={styles.wordmark}>Get a Room</p>
      </header>

      <main className={styles.main}>
        <div className={styles.hero}>
          <h1>Find an empty classroom to study in.</h1>
          <p className={styles.lede}>
            Get a Room shows UC Berkeley classrooms with no class scheduled, and
            how long they stay free.
          </p>
        </div>

        <AvailabilitySearch />

        <p className={styles.note}>
          Based on the <a href="https://classes.berkeley.edu">class schedule</a>
          , not who's actually in the room. Rooms may be locked, and can't be
          reserved.
        </p>
      </main>
    </div>
  )
}

export default LandingPage
