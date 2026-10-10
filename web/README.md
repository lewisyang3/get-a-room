# Get a Room Web

Frontend for **Get a Room**: helps UC Berkeley students find classrooms with no
scheduled class, so they can use them to study. It's a React + TypeScript app
built with Vite, and it reads availability from the
[Get a Room API](https://github.com/get-a-room-berkeley/get-a-room-api).

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

## Campus map

A map shows each building with how many rooms it has free for the current
search. It needs a Mapbox token (`VITE_MAPBOX_TOKEN`, see Configuration), and
search is disabled until one is set.

- **Counts follow the search.** They use the same time, minimum and room or
  building search as the list, at the same minute. Every building keeps its
  count while one is selected. A faded "0" means no room is free there. A
  plain dot means the counts haven't loaded or couldn't be loaded.
- **Choosing a building** on the map filters the results to it. Choosing it
  again, or Show all buildings under the results summary, shows every
  building.
- **Layout.** On wide screens (64rem and up) the map sits beside the
  results and stays in view as they scroll. On narrower screens a List / Map
  switch shows one at a time, and choosing a building goes back to the list.
- **If the map can't load.** Where the browser can't run it (no WebGL), or
  Mapbox can't load it (for example, it rejects the token), a notice says so,
  the switch is left out, and the list fills the page. Typing a building's
  name in the search still finds its rooms. Without any building locations,
  the map is left out with no notice. Mapbox GL loads only when the map is
  shown, in a separate chunk.

The map uses Mapbox's Standard style, with day lighting in light mode and night
lighting in dark mode. Building locations come from `GET /buildings`, and the
counts from `GET /availability/buildings`.

## Accessibility

The page aims for WCAG 2.2 AA on phones and desktops.

- **Keyboard:** every control can be reached with Tab. The segmented controls
  are native radio buttons, so the arrow keys move between options. When Show
  more loads rooms, focus moves to the first new room. When Try again or Show
  all buildings succeeds, focus moves to the results heading.
- **Screen readers:** controls are labelled, filters are grouped under their
  names, and each building's rooms sit under a heading. The results summary
  is a live region, so a changed filter announces the new room count.
- **Map:** each building on the map is a button named with its count, e.g.
  "Evans: 3 rooms free". It's marked pressed when selected, and it's reachable
  with Tab. Everything the map does is also available without it: the list
  shows each building's rooms, the Room or building search finds a building
  by name, and Show all buildings clears a building chosen on the map.
- **Zoom and small screens:** the page reflows down to 320 CSS px (400% zoom)
  without sideways scrolling. Text follows the browser's font size. Buttons,
  fields and the Directions links have tap targets at least 44px tall.
- **Display settings:** light and dark mode, increased contrast and reduced
  motion are respected. Text colors meet AA contrast in each.

**How it's checked:** `npm test` runs [axe](https://github.com/dequelabs/axe-core)
over the landing page and each search state (loading, results, empty, error,
and the map in both layouts). jsdom can't measure color contrast, so the color
tokens in `src/index.css` are chosen to meet AA. The
layout at each width, the keyboard order and Chrome's accessibility tree are
checked by hand.

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
the tests and the build on every push and on pull requests to `main`.
