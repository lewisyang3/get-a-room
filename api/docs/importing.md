# Importing a term

Imports are run by hand with the operator CLI (`python -m ingestion.cli --help`).
With the database migrated, create the term once, pointing it at the term's
page on classes.berkeley.edu, then import it. The source URL must be exactly
`https://classes.berkeley.edu/taxonomy/term/{id}`, and each taxonomy id can
belong to only one term. Check the id before importing: the page's heading
names its term (8588 is "2026 Fall-1"; 8573 is "2025 Fall-1"), and its section
links start with that term, e.g. `/content/2026-fall-…`.

```bash
python -m ingestion.cli term create --name "Fall 2026" \
    --start 2026-08-26 --end 2026-12-11 \
    --source-url https://classes.berkeley.edu/taxonomy/term/8588
python -m ingestion.cli term list
python -m ingestion.cli import run "Fall 2026"
```

Terms can be referred to by id or exact name. `term create` also takes
`--timezone` (an IANA zone; default `America/Los_Angeles`) and
`--status active|archived`;
`term set-status "Fall 2026" archived` retires a term, after which
`import run` refuses it unless given `--allow-archived`.

Inside Docker Compose, prefix commands with `docker compose run --rm api`,
e.g. `docker compose run --rm api python -m ingestion.cli term list`.

`import run` scrapes every section in the term, one request per
`SCRAPER_RATE_LIMIT_SECONDS` (a full term is about 11,000 requests, roughly
8-12 hours depending on how fast Berkeley responds), logs progress every 100
sections, recomputes the term's availability, and records the run as an
`ImportRun`. Nothing is written until the scrape finishes; then the whole run
is saved in one short transaction, so a dropped database connection during
the scrape doesn't fail it. A completed run also
stamps the term's `processed_at` (shown as `PROCESSED` in `term list`); a
failed run leaves it unchanged, so it always says when the term's current data
was imported. Re-running is safe: meetings are upserted, and ones the term no
longer lists are removed.

A request that times out or loses its connection, or gets an error status
other than 401, 403 or 404 back, is retried after 5s, 30s and 2 min, with a
warning logged each time, so an outage of a couple of
minutes at classes.berkeley.edu doesn't fail the run. A failed listing page
still fails the whole run once its retries are used up, since the sections
on it would be missed. On a laptop, keep it awake for the whole run, e.g.
`caffeinate -is python -m ingestion.cli import run "Fall 2026"` on macOS.

Options:

- `--max-retire-fraction F` (default `0.5`) — abort, keeping the existing
  data, if the run would remove more than this fraction of the term's
  sections. A run that finds no sections at all always aborts. Pass `1.0` when
  a genuinely large change is expected.
- `--max-pages N` (default `5000`) — fail instead of paging the term listing
  forever.
- `--rate-limit-seconds S` — override `SCRAPER_RATE_LIMIT_SECONDS`.
- `--parser-version V` — recorded on the `ImportRun` for debugging (at most 50
  characters).

Exit codes, for scripts and schedulers:

| Code | Meaning |
|---|---|
| 0 | Import completed. |
| 1 | Import failed or aborted, and the previously imported data is left untouched. A `FAILED` `ImportRun` is recorded, unless the database itself was unreachable; the log then says `import (not recorded)` and includes the traceback. |
| 2 | Usage error: bad arguments, unknown or archived term, or a term without a usable source URL. Nothing ran. |
| 3 | Import completed, but some sections failed to fetch or parse, so removal of classes that disappeared was skipped. Re-run once the source recovers. |
| 130, 143 | Interrupted by Ctrl-C (130) or SIGTERM (143, e.g. `docker stop` or a scheduler timeout). Handled like exit 1: a `FAILED` `ImportRun` is recorded and previous data is untouched. See the note below. |

A `FAILED` run is recorded for an interrupt only once the signal is actually
handled. A request already in flight has to finish first, which can take up to
`SCRAPER_TIMEOUT_SECONDS` (30s by default). Anything that escalates to
`SIGKILL` before then - including `docker stop`, which waits only 10s by
default - kills the import with no record, since `SIGKILL` can't be handled.
Give whatever stops an import a longer grace period than the request timeout:
for example `docker stop -t 60`, `stop_grace_period: 60s` in Compose, or your
scheduler's equivalent.

## Checking an import

```bash
python -m ingestion.cli import report "Fall 2026"
```

prints a data-quality report for the term's current data. Run it after each
import. It exits with 2 if the term has no completed import. It shows:

- **Last import:** sections read, imported, rejected and failed, and the
  rejections by reason, most common first. Runs from before reasons were
  recorded say so.
- **Coverage:** buildings, the covered ones still missing coordinates (add them
  to `data/building_locations.csv`), rooms, sections and meetings by type, and
  meetings outside 07:00-22:00, the hours availability covers.
- **Duplicate checks:** exact duplicates are blocked by database constraints,
  so this lists likely ones they can't catch: room numbers in one building that
  differ only in case, spacing, punctuation or leading zeros, building names
  that differ only by a word like "Hall", and different sections meeting in
  one room at overlapping times. Overlaps are usually cross-listed courses or
  lab sections sharing a room, but a wrong room parse looks the same.
- **Rooms in use, by building.**
- **Sample availability:** how many searchable rooms are free Monday to Friday
  at 10:00, 14:00 and 18:00, and a few rooms free on Monday at 10:00.

Rejection reasons:

| Reason | Meaning |
|---|---|
| `section_type_not_room_occupying:TYPE` | Not a lecture, discussion, lab, group, recitation, seminar or studio section (e.g. `IND` independent study, `TUT` tutorial), so it isn't tied to a scheduled room. |
| `no_meetings` | No meeting days and times. |
| `online` | Taught online. |
| `general_assignment_requested` | No room assigned yet ("Requested General Assignment"). |
| `missing_location` | No location given. |
| `unparseable_location` | A location that isn't a building and room, e.g. an off-campus site. |

## Known limitations

- **Concurrent runs aren't prevented.** Two `import run` commands for the same
  term can run at the same time, and two `term create` commands run at once can
  both pass the taxonomy-id check and create two terms for one id. The real
  fix is a unique taxonomy-id column (a migration) plus the non-overlapping
  scheduled runs planned in GAR-045; until then, run one command at a time.
- **An interrupt during the final commit can leave two records.** If Ctrl-C or
  SIGTERM lands after the database has committed the `COMPLETED` run but before
  the commit call returns, a `FAILED` row is added beside it. The data itself
  is the completed import's.
- **Source URLs are validated strictly.** A term's URL must be exactly
  `https://classes.berkeley.edu/taxonomy/term/{id}`; a stored term that doesn't
  match (e.g. one created before this rule) fails `import run` with exit 2.
  Before deploying to a database that already has terms, check their URLs with
  `python -m ingestion.cli term list`.

