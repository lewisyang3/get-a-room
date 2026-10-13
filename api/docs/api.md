# API reference

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

