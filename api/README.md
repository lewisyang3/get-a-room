# Get a Room API

The backend for **Get a Room**, which helps UC Berkeley students find a
classroom to study in. It serves the site at **https://getaroomberkeley.me**.

## The problem

Classrooms sit empty for hours between classes, and they're often the quietest
place on campus to study. But there's no easy way to know which ones are free
right now, or how long they'll stay that way, short of walking the halls and
checking doors.

## How Get a Room solves it

Every class's room and meeting times are published in Berkeley's class
schedule. If a room has no class scheduled now, it's free until its next one.

```
classes.berkeley.edu ──import──▶ Postgres ◀── this API ◀── web app ◀── students
```

This folder does three things:

1. **Imports a term.** An operator runs the import by hand once per term. It
   scrapes every section in the term from classes.berkeley.edu and keeps those
   that meet in a scheduled room: lectures, discussions, labs, seminars and
   so on. Then it stores each room's weekly meeting times.
2. **Works out free time.** A room is free between its meetings, within
   07:00–22:00 in the term's timezone.
3. **Answers questions about it** through three read-only endpoints:
   - `/availability`: which rooms are free at a given time, and until when.
   - `/availability/buildings`: how many rooms are free in each building, for
     the map.
   - `/buildings`: every building, with its location.

The [web app](../web) is the
search page and campus map that students use; it calls these endpoints. The API
runs on Heroku with Heroku Postgres, and the site on GitHub Pages.

Availability is derived from **scheduled** course data — this does not guarantee a
room is unlocked, permitted for student use, or actually unoccupied. The web
README's
[What it can and can't tell you](../web/README.md#what-it-can-and-cant-tell-you)
has the full list.

## Quick start

Prerequisites: Docker and Docker Compose. From this folder:

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head    # once per new database
```

The API is then on `http://localhost:8000`, with interactive docs at
`http://localhost:8000/docs`. It has no data until a term is imported. Check the
term's taxonomy id first (see [Importing a term](docs/importing.md)), and expect
a full import to take 8–12 hours:

```bash
docker compose exec api python -m ingestion.cli term create --name "Fall 2026" \
    --start 2026-08-26 --end 2026-12-11 \
    --source-url https://classes.berkeley.edu/taxonomy/term/8588
docker compose exec api python -m ingestion.cli import run "Fall 2026"
docker compose exec api python -m ingestion.cli buildings set-locations
curl 'http://localhost:8000/availability?term_id=1'
```

## Code layout

- `app/` — FastAPI application (`main.py`), config (`config.py`), DB setup (`db.py`),
  API routers (`app/api/`), and SQLAlchemy models (`app/models/`).
- `alembic/` — database migrations.
- `ingestion/` — Berkeley schedule scraper, parser, import into the database
  (`persist.py`'s `run_import`), and the operator CLI (`cli.py`).
- `data/building_locations.csv` — building coordinates, kept by hand.
- `tests/` — pytest suite.

## Docs

- [Importing a term](docs/importing.md): running and checking an import, exit
  codes, rejection reasons and known limitations.
- [API reference](docs/api.md): the three endpoints, their parameters and
  responses.
- [Building locations](docs/building-locations.md): where coordinates come from
  and how to update them.
- [Development](docs/development.md): local setup, migrations, tests, lint, CI
  and environment variables.
- [Deploying to Heroku](docs/deployment.md): setting up and deploying the
  production API, and importing into it.
- [Design](docs/design.md): how the pipeline, schema and interval logic work and
  why, the Fall 2026 data-quality report, limitations and open questions.
