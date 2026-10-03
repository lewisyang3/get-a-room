import styles from './LandingPage.module.css'

type Point = {
  title: string
  body: string
}

// \u00a0 keeps a time and its a.m./p.m. on the same line.
const HOW_IT_WORKS: Point[] = [
  {
    title: 'Class schedule',
    body: "Free time is worked out from the term's scheduled classes.",
  },
  {
    title: 'Campus time',
    body: 'Every time is Pacific time, the same clock as campus.',
  },
  {
    title: '7\u00a0a.m. to 10\u00a0p.m.',
    body: 'Availability covers 7\u00a0a.m. to 10\u00a0p.m., to the minute.',
  },
]

const LIMITATIONS: Point[] = [
  {
    title: 'Scheduled, not live',
    body: "It doesn't track who is actually in a room, so a free room may already be in use.",
  },
  {
    title: 'No guarantee of access',
    body: 'A room with no class may still be locked or not open to students.',
  },
  {
    title: 'No reservations',
    body: "Rooms can't be booked here. It's first come, first served.",
  },
  {
    title: "Holidays and breaks aren't included",
    body: 'Check the academic calendar before heading out.',
  },
]

function PointList({
  points,
  className,
}: {
  points: Point[]
  className: string
}) {
  return (
    <ul className={className}>
      {points.map((point) => (
        <li key={point.title} className={styles.point}>
          <h3>{point.title}</h3>
          <p className={styles.secondary}>{point.body}</p>
        </li>
      ))}
    </ul>
  )
}

function LandingPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <p className={styles.wordmark}>Get a Room</p>
      </header>

      <main className={styles.main}>
        <section className={styles.hero} aria-labelledby="hero-title">
          <h1 id="hero-title">Find an empty classroom to study in.</h1>
          <p className={styles.lede}>
            Get a Room shows UC Berkeley classrooms with no class scheduled, and
            how long they stay free.
          </p>
        </section>

        <section aria-labelledby="how-it-works-title">
          <h2 id="how-it-works-title" className={styles.sectionTitle}>
            How it works
          </h2>
          <PointList points={HOW_IT_WORKS} className={styles.grid} />
        </section>

        <section
          className={styles.callout}
          aria-labelledby="before-you-go-title"
        >
          <h2 id="before-you-go-title" className={styles.sectionTitle}>
            Before you go
          </h2>
          <p className={styles.calloutIntro}>
            Get a Room only knows the class schedule, so keep these in mind.
          </p>
          <PointList points={LIMITATIONS} className={styles.stack} />
        </section>
      </main>

      <footer className={styles.footer}>
        <p className={styles.secondary}>
          Availability comes from the UC Berkeley class schedule at{' '}
          <a href="https://classes.berkeley.edu">classes.berkeley.edu</a>.
        </p>
      </footer>
    </div>
  )
}

export default LandingPage
