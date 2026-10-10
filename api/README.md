# Get a Room API

Backend for **Get a Room**: helps UC Berkeley students find scheduled classroom
space that's free to study in right now, how long it stays free, and where it is.

## Architecture

- `app/` — FastAPI application (`main.py`), config (`config.py`), DB setup (`db.py`),
  API routers (`app/api/`), and SQLAlchemy models (`app/models/`).
- `alembic/` — database migrations.
- `ingestion/` — Berkeley schedule scraper, parser, import into the database
  (`persist.py`'s `run_import`), and the operator CLI (`cli.py`).
- `tests/` — pytest suite.

Availability is derived from **scheduled** course data — this does not guarantee a
room is unlocked, permitted for student use, or actually unoccupied.

## Local setup

Prerequisites: Docker and Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

This starts a PostgreSQL container and the API on `http://localhost:8000`.

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`
- Readiness check: `http://localhost:8000/ready`. Returns 503 when the API
  can't reach the database; use this as a host's health check URL.

## Database migrations

With the `db` service running (`docker compose up db -d`):

```bash
pip install -r requirements.txt
alembic upgrade head
```

To generate a new migration after changing models in `app/models/`:

```bash
alembic revision --autogenerate -m "describe the change"
```

New model modules must be imported and re-exported from `app/models/__init__.py`
(see the comment there) — Alembic only sees model classes that have actually
been imported somewhere, and only imports `app.models` itself. A model defined
in a module that's never imported won't show up in autogenerate.

Keep migrations linear (one head) and make every `downgrade()` fully undo its
`upgrade()` — CI checks both (see below).

## Importing a term

Imports are run by hand with the operator CLI (`python -m ingestion.cli --help`).
With the database migrated, create the term once, pointing it at the term's
page on classes.berkeley.edu, then import it. The source URL must be exactly
`https://classes.berkeley.edu/taxonomy/term/{id}`, and each taxonomy id can
belong to only one term:

```bash
python -m ingestion.cli term create --name "Fall 2026" \
    --start 2026-08-19 --end 2026-12-18 \
    --source-url https://classes.berkeley.edu/taxonomy/term/8573
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
`SCRAPER_RATE_LIMIT_SECONDS` (a full term is about 11,000 requests, roughly 8
hours), logs progress every 100 sections, recomputes the term's
availability, and records the run as an `ImportRun`. A completed run also
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

### Known limitations

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

## Querying availability

`GET /availability` returns the rooms with no scheduled class at a given time,
how long each stays free, and the room and building ids. Interactive docs are at
`/docs` while the API is running.

```bash
# Right now, in the term's own timezone:
curl 'http://localhost:8000/availability?term_id=1'
# Friday, October 17 at 14:30, in the term's timezone:
curl 'http://localhost:8000/availability?term_id=1&at=2025-10-17T14:30'
# Fridays at 14:30, rooms free for at least 90 minutes:
curl 'http://localhost:8000/availability?term_id=1&day_of_week=4&time=14:30&minimum_minutes=90'
# Dwinelle 242, right now:
curl 'http://localhost:8000/availability?term_id=1&building=dwinelle&room=242'
# Right now, nearest to a point first:
curl 'http://localhost:8000/availability?term_id=1&near_latitude=37.8736&near_longitude=-122.2577'
```

Responses are one page of results:

```json
{"total": 42, "limit": 50, "offset": 0,
 "date": "2025-10-17", "day_of_week": 4, "time": "14:30",
 "results": [{"room_id": 7, "building_id": 2, "building_code": "DWINELLE",
              "building_name": "Dwinelle", "room_number": "242",
              "available_from": "14:30", "available_until": "17:00",
              "available_minutes": 150, "distance_meters": null}]}
```

- Say when to search in one of three ways (combining them is a 422):
  - `at`: a date and time, e.g. `2025-10-17T14:30`. Without a UTC offset it's
    a clock time in the term's `timezone`; with one (`Z`, `+09:00`) it's
    converted there. A date with no time means midnight.
  - `day_of_week` (0 = Monday) and `time`, together: that time every week.
  - Neither: right now.

  Searches always use the local clock time in the term's timezone, so daylight
  saving time doesn't shift results. Every search is to the minute: seconds
  are ignored, so `10:00:30` searches `10:00`. The response's `date`,
  `day_of_week` and `time` are what was searched (`date` is `null` for a weekly
  search).
- A date outside the term's start and end dates returns no rooms, whether it
  comes from `at` or is today's date in a "now" search. Past dates within the
  term work.
- The schedule doesn't know about academic holidays or breaks: a date during
  one shows that weekday's normal classes.
- Availability only covers 07:00–22:00; searches outside it return no rooms.
- `minimum_minutes` defaults to 60 (1–1440). An unknown term is a 404.
- Filters, all optional and all applied together:
  - `building_id`
  - `building_code`: exact match, ignoring case
  - `building`: part of the building name, ignoring case
  - `room`: exact room number, ignoring case

  A filter that matches nothing returns `total: 0`, not an error.
- Results are sorted by building name, then room number. `limit` (default
  50, at most 200) and `offset` select a page; `total` counts every match.
- `near_latitude` and `near_longitude`, together, sort by distance from that
  point instead: nearest building first, buildings with no coordinates last,
  and each building's rooms kept together. Each result's `distance_meters` is
  the building's distance, rounded to the metre, or `null` without a point or
  coordinates. Distances use a flat-earth approximation, within 1% across a
  campus. Giving only one of the two is a 422.

Errors are `{"detail": ...}`. An unknown term is a 404 with a message. Any
invalid request is a 422 with a list of problems, each with a `loc` naming the
parameter at fault:

```json
{"detail": [{"type": "value_error", "loc": ["query", "time"],
             "msg": "time is required with day_of_week", "input": null}]}
```

`/docs` is the full reference: every parameter, response field, example, and
error.

## Summarising availability by building

`GET /availability/buildings` takes the same search as `/availability`, except
`limit` and `offset`, and returns one row per building with a room free: how
many rooms are free and the longest any of them stays free. It's what a map
needs for per-building counts, without paging through every room.

```bash
# Right now, nearest to a point first:
curl 'http://localhost:8000/availability/buildings?term_id=1&near_latitude=37.8736&near_longitude=-122.2577'
```

```json
{"date": "2025-10-17", "day_of_week": 4, "time": "14:30",
 "results": [{"building_id": 2, "building_code": "DWINELLE",
              "building_name": "Dwinelle", "free_rooms": 6,
              "longest_free_until": "22:00", "longest_free_minutes": 450,
              "distance_meters": null}]}
```

- Every building is counted, not one page's worth. A building's `free_rooms`
  is the `total` `/availability` reports for the same search with that
  `building_id`.
- `longest_free_until` is the latest `available_until` among those rooms, and
  `longest_free_minutes` the minutes from the time searched until then.
- Buildings with no matching room are left out; `/buildings` lists them all.
- Sorting, `distance_meters`, the search moment, and errors work as for
  `/availability`: by name, or nearest first with `near_latitude` and
  `near_longitude`.

## Listing buildings

`GET /buildings` returns every building `/availability` searches: buildings
inside the coverage area with at least one room in use. It takes no parameters
and isn't paged.

```bash
curl 'http://localhost:8000/buildings'
```

```json
{"results": [{"building_id": 2, "building_code": "DWINELLE",
              "building_name": "Dwinelle",
              "latitude": 37.8705, "longitude": -122.2606}]}
```

- Buildings are sorted by name. `latitude` and `longitude` are `null` when
  unknown.
- The fields match `/availability`'s, so a building's `building_id` or
  `building_code` works as the `/availability` filter of the same name.
- A listed building can still have no free room at a given time.

## Building locations

Berkeley's section pages don't give building coordinates, so they're kept by
hand in [`data/building_locations.csv`](data/building_locations.csv)
(`name,latitude,longitude`) and applied to the database with:

```bash
python -m ingestion.cli buildings set-locations            # the repo's CSV
python -m ingestion.cli buildings set-locations --file other.csv
```

- Names are matched the way imports key buildings, ignoring case and
  punctuation, so use the building name as it appears in the class schedule's
  locations (`Dwinelle`, `Valley Life Sciences`).
- It's safe to re-run, and imports never change coordinates. Run it again
  after an import adds buildings: it lists covered buildings that still have
  no coordinates (they sort last by distance), and CSV names that matched no
  building.
- An invalid CSV changes nothing and exits 2, naming the line at fault.
- Coordinates come from [OpenStreetMap](https://www.openstreetmap.org/)
  (© OpenStreetMap contributors, ODbL), at each building's centroid, to 5
  decimal places (about a metre). Barrows, Kroeber and LeConte were renamed,
  and their names in the schedule aren't known yet, and Genetics & Plant
  Biology had no OpenStreetMap match, so they're left out until a real import
  shows how the schedule names them.

## Running tests and lint locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up db -d   # the persistence tests need a real Postgres

pytest
ruff check .
ruff format .           # or `ruff format --check .` to check without changing files
```

Tests never touch your dev database: they create and drop a separate
`<database>_test` database on the same server. If Postgres isn't reachable,
the database-backed tests are skipped; set `REQUIRE_TEST_DB=1` to make them
fail instead (CI does this).

Ruff and pytest are configured in `pyproject.toml` (88-character lines). The
one-off repo-wide format commit is listed in `.git-blame-ignore-revs`; run
`git config blame.ignoreRevsFile .git-blame-ignore-revs` to skip it in local
`git blame`.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and on pull requests to `main`:

- **lint** — `ruff check .` and `ruff format --check .`
- **test** — against a `postgres:16` service: exactly one Alembic head,
  `alembic upgrade head` from an empty database, `alembic check` (no drift
  between models and migrations), `alembic downgrade base` followed by
  `alembic upgrade head`, then `pytest` with `REQUIRE_TEST_DB=1`

## Environment variables

See `.env.example` for the full list, including `DATABASE_URL`, `APP_ENV`,
`ALLOWED_ORIGINS`, and scraper rate-limit/timeout settings.

`DATABASE_URL` may also use the `postgres://` scheme, as Heroku sets it; it's
read as `postgresql+psycopg2://`. Connections to the database time out after
5 seconds.

The Docker image's server listens on `$PORT`, or on 8000 if `PORT` isn't set.

## Deploying to Heroku

The API runs on Heroku's container stack with Heroku Postgres. `heroku.yml`
builds the `Dockerfile`, and its release phase runs `alembic upgrade head`
before each new version starts; if a migration fails, the release is cancelled
and the previous version keeps serving.

One-time setup:

```bash
heroku create <app> --stack container
heroku addons:create heroku-postgresql:essential-0 -a <app>   # sets DATABASE_URL
heroku config:set APP_ENV=production \
  ALLOWED_ORIGINS=https://getaroomberkeley.me -a <app>
```

Deploy by pushing `main` to the `heroku` remote:

```bash
git push heroku main
```

Check `https://<app>.herokuapp.com/ready` afterwards; it returns 503 if the
database can't be reached.
