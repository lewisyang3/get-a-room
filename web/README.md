# Get a Room Web

**Get a Room** helps UC Berkeley students find a classroom to study in. It's
live at **https://getaroomberkeley.me**.

## The problem

Classrooms sit empty for hours between classes, and they're often the
quietest place on campus to study. But there's no easy way to know which ones
are free right now, or how long they'll stay that way, short of walking the
halls and checking doors.

## How Get a Room solves it

Every class's room and meeting times are published in Berkeley's class
schedule. If a room has no class scheduled now, it's free until its next one.
Get a Room collects the schedule once per term and answers "which rooms are
free, and until when?" for any time.

```
classes.berkeley.edu ──import──▶ Postgres ◀── API ◀── this site ◀── students
```

It's split across two repos:

- **[get-a-room-api](https://github.com/get-a-room-berkeley/get-a-room-api)**
  imports a term from the class schedule, stores when each room is booked,
  and answers availability questions: free rooms at a time (`/availability`),
  counts per building (`/availability/buildings`) and building locations
  (`/buildings`). It runs on Heroku with Postgres.
- **get-a-room-web** (this repo) is the search page. Pick a time and how long
  you need a room, and it lists the free rooms grouped by building, with how
  long each stays free, next to a campus map. It's a React + TypeScript app
  built with Vite and served as a static site from GitHub Pages.

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

## Quick start

Check out both repos side by side (`get-a-room/get-a-room-api` and
`get-a-room/get-a-room-web`), then from this repo:

```bash
cp ../get-a-room-api/.env.example ../get-a-room-api/.env   # once
docker compose up --build
docker compose exec api alembic upgrade head               # once per new database
```

The site is then at `http://localhost:3000` and the API at
`http://localhost:8000`. Search stays off until a term is imported and
`VITE_TERM_ID` and `VITE_MAPBOX_TOKEN` are set; see
[Development](docs/development.md).

## Docs

- [Development](docs/development.md): running locally, configuration, scripts
  and CI.
- [Deployment](docs/deployment.md): how the live site is built and published,
  and its settings.
- [Campus map](docs/campus-map.md): what the map shows and how it behaves.
- [Accessibility](docs/accessibility.md): what the page supports and how it's
  checked.
