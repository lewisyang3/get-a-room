from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas.availability import AvailabilityPage, AvailabilityResponse
from app.db import get_db
from app.models.models import AvailabilityInterval, Building, Room, Term

# Creates a router for availability-related endpoints.
router = APIRouter(
    prefix="/availability",
    tags=["availability"],
)


# Returns the current time; tests override this to pin "now".
def get_now() -> datetime:
    return datetime.now(timezone.utc)


# Converts a time of day to minutes since midnight, for duration math.
def _minutes_since_midnight(value: time) -> float:
    return (
        value.hour * 60
        + value.minute
        + (value.second + value.microsecond / 1_000_000) / 60
    )


# Trims a text filter, rejecting one that is only whitespace.
def _clean_text_filter(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise HTTPException(status_code=422, detail=f"{name} must not be blank")
    return value


# The moment a search looks at, in the term's timezone.
class _SearchMoment(NamedTuple):
    # The local date searched, or None for a weekday-and-time search.
    date: date | None
    day_of_week: int
    time: time
    # True when the date is outside the term, so no rooms can match.
    outside_term: bool


# Turns a local date and time into the moment to search.
def _local_moment(term: Term, local: datetime) -> _SearchMoment:
    return _SearchMoment(
        date=local.date(),
        day_of_week=local.weekday(),
        time=local.time(),
        # Outside the term, its schedule doesn't describe the rooms.
        outside_term=not term.start_date <= local.date() <= term.end_date,
    )


# Works out which weekday and time to search: the ones given, or right now.
def _resolve_search(
    term: Term,
    now: datetime,
    day_of_week: int | None,
    requested_time: time | None,
) -> _SearchMoment:
    # A weekday and time search every week of the term, so there's no date.
    if day_of_week is not None and requested_time is not None:
        return _SearchMoment(None, day_of_week, requested_time, False)
    # Otherwise searches right now in the term's timezone, to the minute.
    local_now = now.astimezone(ZoneInfo(term.timezone))
    return _local_moment(term, local_now.replace(second=0, microsecond=0))


# Returns rooms that are available at a requested time, or right now.
@router.get(
    "",
    response_model=AvailabilityPage,
    responses={404: {"description": "The term does not exist."}},
)
def get_available_rooms(
    # Identifies the academic term being searched.
    term_id: int = Query(..., description="The term to search."),
    # Uses 0 for Monday through 6 for Sunday.
    day_of_week: int | None = Query(
        None,
        ge=0,
        le=6,
        description=(
            "Weekday to search, 0 = Monday ... 6 = Sunday. Give together with "
            "`time`; omit both to search right now."
        ),
    ),
    # Specifies the time at which the user wants to search.
    requested_time: time | None = Query(
        None,
        alias="time",
        description=(
            "Local time of day in the term's timezone, e.g. `14:30`, without a "
            "UTC offset. Give together with `day_of_week`; omit both to search "
            "right now."
        ),
    ),
    # Removes availability gaps shorter than this value.
    minimum_minutes: int = Query(
        60,
        ge=1,
        le=24 * 60,
        description="Only return rooms free for at least this many minutes.",
    ),
    # Optionally limits results to one building.
    building_id: int | None = Query(
        None, description="Only return rooms in this building."
    ),
    # Optionally limits results to one building code, ignoring case.
    building_code: str | None = Query(
        None,
        min_length=1,
        description="Only return rooms in the building with this exact code, "
        "ignoring case, e.g. `dwinelle`.",
    ),
    # Optionally limits results to buildings whose name contains this text.
    building: str | None = Query(
        None,
        min_length=1,
        description="Only return rooms in buildings whose name contains this "
        "text, ignoring case, e.g. `dwin`.",
    ),
    # Optionally limits results to one room number, ignoring case.
    room: str | None = Query(
        None,
        min_length=1,
        description="Only return rooms with exactly this room number, ignoring "
        "case, e.g. `242`.",
    ),
    # Caps how many rooms one response returns.
    limit: int = Query(50, ge=1, le=200, description="Rooms per page, 1-200."),
    # Skips this many rooms, for later pages.
    offset: int = Query(0, ge=0, description="Rooms to skip before this page."),
    # Gets a database session from FastAPI.
    db: Session = Depends(get_db),
    # Gets the current time from FastAPI.
    now: datetime = Depends(get_now),
) -> AvailabilityPage:
    """Rooms with no scheduled class at the requested time, one page at a time.

    With neither `day_of_week` nor `time`, searches right now in the term's
    own timezone, and returns no rooms when today is outside the term's
    dates. Availability only covers 07:00-22:00, so searches outside that
    window return no rooms. All filters apply together; results are sorted
    by building name, then room number.
    """
    # Requires the weekday and time together, or neither.
    if (day_of_week is None) != (requested_time is None):
        raise HTTPException(
            status_code=422,
            detail="day_of_week and time must be given together, or both omitted",
        )
    # Rejects times with a UTC offset; times are local to the term.
    if requested_time is not None and requested_time.tzinfo is not None:
        raise HTTPException(
            status_code=422,
            detail="time must be a local time in the term's timezone, "
            "without a UTC offset",
        )

    # Trims the text filters, rejecting ones that are only whitespace.
    building_code = _clean_text_filter("building_code", building_code)
    building = _clean_text_filter("building", building)
    room = _clean_text_filter("room", room)

    # Looks up the term so a missing one isn't mistaken for "no rooms free".
    term = db.get(Term, term_id)
    if term is None:
        raise HTTPException(status_code=404, detail=f"term {term_id} not found")

    # Resolves the weekday and time to search, in the term's timezone.
    moment = _resolve_search(term, now, day_of_week, requested_time)
    day_of_week, requested_time = moment.day_of_week, moment.time

    # Builds a page of results for the resolved weekday and time.
    def page(total: int, results: list[AvailabilityResponse]) -> AvailabilityPage:
        return AvailabilityPage(
            total=total,
            limit=limit,
            offset=offset,
            day_of_week=day_of_week,
            time=requested_time.strftime("%H:%M"),
            results=results,
        )

    # Finds the earliest end time that still leaves the minimum free time.
    threshold = datetime.combine(date.min, requested_time) + timedelta(
        minutes=minimum_minutes
    )
    # A minimum that runs past midnight can't be met by any room.
    if moment.outside_term or threshold.date() != date.min:
        return page(0, [])

    # Builds a query joining availability intervals to rooms and buildings.
    statement = (
        select(AvailabilityInterval, Room, Building)
        .join(Room, AvailabilityInterval.room_id == Room.room_id)
        .join(Building, Room.building_id == Building.building_id)
        .where(
            AvailabilityInterval.term_id == term_id,
            AvailabilityInterval.day_of_week == day_of_week,
            AvailabilityInterval.start_time <= requested_time,
            AvailabilityInterval.end_time > requested_time,
            # Keeps only intervals at least minimum_minutes long from now on.
            AvailabilityInterval.end_time >= threshold.time(),
            Room.in_use.is_(True),
            Building.included_in_coverage.is_(True),
        )
    )

    # Adds the building filter only when one was provided.
    if building_id is not None:
        statement = statement.where(Building.building_id == building_id)
    # Adds the remaining filters the same way; they all apply together.
    if building_code is not None:
        statement = statement.where(
            func.lower(Building.short_code) == building_code.lower()
        )
    if building is not None:
        # autoescape matches % and _ literally instead of as wildcards.
        statement = statement.where(Building.name.icontains(building, autoescape=True))
    if room is not None:
        statement = statement.where(func.lower(Room.room_number) == room.lower())

    # Counts every match, before paging.
    total = db.scalar(select(func.count()).select_from(statement.subquery()))

    # Sorts by building name and room number, then id as a tiebreak, and
    # takes one page so the order stays the same from page to page.
    statement = (
        statement.order_by(Building.name, Room.room_number, Room.room_id)
        .limit(limit)
        .offset(offset)
    )

    # Runs the query and retrieves the matching rows.
    rows = db.execute(statement).all()

    # Stores the formatted API results.
    results: list[AvailabilityResponse] = []

    # Processes each available interval.
    for interval, matched_room, matched_building in rows:
        # Calculates the number of available minutes.
        available_minutes = int(
            _minutes_since_midnight(interval.end_time)
            - _minutes_since_midnight(requested_time)
        )

        # Adds the room to the response.
        results.append(
            AvailabilityResponse(
                room_id=matched_room.room_id,
                building_id=matched_building.building_id,
                building_code=matched_building.short_code,
                building_name=matched_building.name,
                room_number=matched_room.room_number,
                available_from=requested_time.strftime("%H:%M"),
                available_until=interval.end_time.strftime("%H:%M"),
                available_minutes=available_minutes,
            )
        )

    # Returns this page of available rooms.
    return page(total, results)
