from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.availability import AvailabilityResponse
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
    return value.hour * 60 + value.minute + value.second / 60


# Returns rooms that are available at a requested time, or right now.
@router.get(
    "",
    response_model=list[AvailabilityResponse],
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
    # Gets a database session from FastAPI.
    db: Session = Depends(get_db),
    # Gets the current time from FastAPI.
    now: datetime = Depends(get_now),
) -> list[AvailabilityResponse]:
    """Rooms with no scheduled class at the requested time.

    With neither `day_of_week` nor `time`, searches right now in the term's
    own timezone, and returns no rooms when today is outside the term's
    dates. Availability only covers 07:00-22:00, so searches outside that
    window return no rooms.
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

    # Looks up the term so a missing one isn't mistaken for "no rooms free".
    term = db.get(Term, term_id)
    if term is None:
        raise HTTPException(status_code=404, detail=f"term {term_id} not found")

    # Resolves "now" to a weekday and time in the term's timezone.
    if day_of_week is None or requested_time is None:
        local_now = now.astimezone(ZoneInfo(term.timezone))
        # Outside the term, its schedule doesn't describe the rooms.
        if not term.start_date <= local_now.date() <= term.end_date:
            return []
        day_of_week = local_now.weekday()
        requested_time = local_now.time().replace(second=0, microsecond=0)

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
            Room.in_use.is_(True),
            Building.included_in_coverage.is_(True),
        )
    )

    # Adds the building filter only when one was provided.
    if building_id is not None:
        statement = statement.where(Building.building_id == building_id)

    # Runs the query and retrieves the matching rows.
    rows = db.execute(statement).all()

    # Stores the formatted API results.
    results: list[AvailabilityResponse] = []

    # Processes each available interval.
    for interval, room, building in rows:
        # Calculates the number of available minutes.
        available_minutes = int(
            _minutes_since_midnight(interval.end_time)
            - _minutes_since_midnight(requested_time)
        )

        # Skips intervals shorter than the requested minimum.
        if available_minutes < minimum_minutes:
            continue

        # Adds the room to the response.
        results.append(
            AvailabilityResponse(
                room_id=room.room_id,
                building_id=building.building_id,
                building_code=building.short_code,
                building_name=building.name,
                room_number=room.room_number,
                available_from=requested_time.strftime("%H:%M"),
                available_until=interval.end_time.strftime("%H:%M"),
                available_minutes=available_minutes,
            )
        )

    # Sorts results by building name and room number, then id as a tiebreak.
    results.sort(
        key=lambda result: (
            result.building_name,
            result.room_number,
            result.room_id,
        )
    )

    # Returns the available rooms.
    return results
