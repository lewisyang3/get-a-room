# Development

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

| Variable            | Default                 | Description                                                                           |
| ------------------- | ----------------------- | ------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Base URL of the API (no trailing slash needed).                                       |
| `VITE_TERM_ID`      | none                    | The term to search, as its `term_id`. Search is disabled until it's set.              |
| `VITE_MAPBOX_TOKEN` | none                    | A Mapbox public token (`pk.…`) for the campus map. Search is disabled until it's set. |

Find a term's id with `python -m ingestion.cli term list` in `get-a-room-api`,
or `docker compose exec api python -m ingestion.cli term list` in the Compose
stack.

Create a Mapbox token at
[account.mapbox.com/access-tokens](https://account.mapbox.com/access-tokens).
It's public, since it's built into the page, so for a deployed site limit it to
that site's URLs. If the site's URL isn't on the token's list, Mapbox rejects it
and visitors see the "map couldn't load" notice. Mapbox's free tier covers a
set number of map loads a month; past that, maps fail to load unless billing is
set up.

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
the tests and the build on every push and on pull requests to `main`. A push to
`main` that passes them also deploys the site (see
[Deployment](deployment.md)).
