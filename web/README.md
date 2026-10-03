# Get a Room Web

Frontend for **Get a Room**: helps UC Berkeley students find classrooms with no
scheduled class, so they can use them to study. It's a React + TypeScript app
built with Vite, and it reads availability from the
[Get a Room API](https://github.com/lewisyang3/get-a-room).

Availability comes from the term's **scheduled** classes, which limits what it
can tell you (see below).

## What it can and can't tell you

Get a Room only knows the class schedule. The landing page sums this up in one
line; the detail is here.

- **Scheduled, not live.** It doesn't track who is actually in a room, so a room
  with no class may already be in use.
- **No guarantee of access.** A room with no class may still be locked or not
  open to students.
- **No reservations.** Rooms can't be booked. It's first come, first served.
- **Holidays and breaks aren't included.** The schedule doesn't know about them,
  so check the academic calendar.
- **Times are Pacific time,** the term's timezone, so daylight saving time
  doesn't shift results.
- **07:00 to 22:00, to the minute.** Availability covers those hours only, and
  seconds are ignored.

## Prerequisites

- Node.js 22 (see `.nvmrc`) and npm, for running the app directly.
- Docker and Docker Compose 2.20 or later, for running the whole stack.

## Running the whole stack with Docker Compose

This repo's `docker-compose.yml` pulls in the API's Compose file from a sibling
checkout, so both repos must sit side by side:

```
get-a-room/
├── get-a-room-api/
└── get-a-room-web/
```

```bash
cp ../get-a-room-api/.env.example ../get-a-room-api/.env   # once
docker compose up --build
docker compose exec api alembic upgrade head               # once per new database
```

This starts PostgreSQL, the API on `http://localhost:8000` and the web app on
`http://localhost:3000`. The source is bind-mounted, so edits reload in the
browser.

Compose names this stack after this directory, so its database volume is
separate from the one `docker compose up` creates in `get-a-room-api/`. Import
a term into this stack with the API's CLI through the `api` service, e.g.
`docker compose exec api python -m ingestion.cli term list` (see the API's
README for the full import steps).

## Running the app directly

With the API running on `http://localhost:8000`:

```bash
npm install
npm run dev
```

The dev server always uses port 3000 and exits if the port is taken, because
`http://localhost:3000` is the API's default allowed CORS origin. To serve the
app from another origin, add it to the API's `ALLOWED_ORIGINS`.

## Configuration

| Variable            | Default                 | Description                                                              |
| ------------------- | ----------------------- | ------------------------------------------------------------------------ |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Base URL of the API (no trailing slash needed).                          |
| `VITE_TERM_ID`      | none                    | The term to search, as its `term_id`. Search is disabled until it's set. |

Find a term's id with `python -m ingestion.cli term list` in `get-a-room-api`,
or `docker compose exec api python -m ingestion.cli term list` in the Compose
stack.

Vite reads `VITE_` variables when it starts the dev server or builds, so restart
or rebuild after changing one. For local overrides, copy `.env.example` to
`.env`, which is gitignored.

## Scripts

| Command                | What it does                                     |
| ---------------------- | ------------------------------------------------ |
| `npm run dev`          | Start the dev server on `http://localhost:3000`. |
| `npm run build`        | Type-check and build to `dist/`.                 |
| `npm run preview`      | Serve the production build locally.              |
| `npm run lint`         | Lint with oxlint.                                |
| `npm run format`       | Format with Prettier.                            |
| `npm run format:check` | Check formatting without changing files.         |
| `npm run typecheck`    | Type-check with `tsc`.                           |
| `npm test`             | Run the tests once with Vitest.                  |
| `npm run test:watch`   | Run the tests in watch mode.                     |

CI (`.github/workflows/ci.yml`) runs lint, the format check, the type check,
the tests and the build on every push and on pull requests to `main`.
