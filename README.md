# Get a Room

**Get a Room** helps UC Berkeley students find a classroom to study in. It's
live at **https://getaroomberkeley.me**.

## The problem

Classrooms sit empty for hours between classes, and they're often the quietest
place on campus to study. But there's no easy way to know which ones are free
right now, or how long they'll stay that way, short of walking the halls and
checking doors.

## How Get a Room solves it

Every class's room and meeting times are published in Berkeley's class
schedule. If a room has no class scheduled now, it's free until its next one.
Get a Room imports the schedule once per term and answers "which rooms are
free, and until when?" for any time.

```
classes.berkeley.edu ──import──▶ Postgres ◀── api/ ◀── web/ ◀── students
```

- **[api/](api)** imports a term from the class schedule, works out when each
  room is free, and serves it through a read-only API. Python, FastAPI and
  PostgreSQL, on Heroku.
- **[web/](web)** is the search page and campus map students use. React and
  TypeScript, built with Vite and served from GitHub Pages.

It only knows the class schedule, so a free room may still be locked or in
use; see [What it can and can't tell you](web/README.md#what-it-can-and-cant-tell-you).

## Quick start

Prerequisites: Docker and Docker Compose 2.20 or later. To run the whole stack:

```bash
cp api/.env.example api/.env   # once
cd web
docker compose up --build
docker compose exec api alembic upgrade head   # once per new database
```

The site is then at `http://localhost:3000` and the API at
`http://localhost:8000`. It has no data until a term is imported; see the
[API's README](api/README.md#quick-start).

## Docs

- [Design](api/docs/design.md): how the whole system works and why, the Fall
  2026 data-quality report, limitations and open questions.
- [API docs](api/README.md#docs) and [web docs](web/README.md#docs).
