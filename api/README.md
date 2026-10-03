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
`SCRAPER_RATE_LIMIT_SECONDS` (a full term is thousands of requests - expect it
to take a while), logs progress every 100 sections, recomputes the term's
availability, and records the run as an `ImportRun`. A completed run also
stamps the term's `processed_at` (shown as `PROCESSED` in `term list`); a
failed run leaves it unchanged, so it always says when the term's current data
was imported. Re-running is safe: meetings are upserted, and ones the term no
longer lists are removed. Options:

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
