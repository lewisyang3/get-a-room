# Get a Room API

Backend for **Get a Room**: helps UC Berkeley students find scheduled classroom
space that's free to study in right now, how long it stays free, and where it is.

## Architecture

- `app/` — FastAPI application (`main.py`), config (`config.py`), DB setup (`db.py`),
  API routers (`app/api/`), and SQLAlchemy models (`app/models/`).
- `alembic/` — database migrations.
- `ingestion/` — Berkeley schedule scraper, parser, and import into the database
  (`persist.py`'s `run_import`).
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
