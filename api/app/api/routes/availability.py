from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.availability import AvailabilityResponse
from app.db import get_db
from app.models.models import AvailabilityInterval, Building, Room

# Creates a router for availability-related endpoints.
router = APIRouter(
    prefix="/availability",
    tags=["availability"],
)


# Returns rooms that are available at a requested time.
@router.get("", response_model=list[AvailabilityResponse])
def get_available_rooms(
    # Identifies the academic term being searched.
    term_id: int,
    # Uses 0 for Monday through 6 for Sunday.
    day_of_week: int = Query(..., ge=0, le=6),
    # Specifies the time at which the user wants to search.
    requested_time: time = Query(..., alias="time"),
    # Removes availability gaps shorter than this value.
    minimum_minutes: int = Query(60, ge=1),
    # Optionally limits results to one building.
    building_id: int | None = None,
    # Gets a database session from FastAPI.
    db: Session = Depends(get_db),
) -> list[AvailabilityResponse]:
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

    # Combines the requested time with an arbitrary date once for duration math.
    start_datetime = datetime.combine(date.today(), requested_time)

    # Processes each available interval.
    for interval, room, building in rows:
        # Combines the interval end time with an arbitrary date.
        end_datetime = datetime.combine(date.today(), interval.end_time)

        # Calculates the number of available minutes.
        available_minutes = int(
            (end_datetime - start_datetime).total_seconds() // 60
        )

        # Skips intervals shorter than the requested minimum.
        if available_minutes < minimum_minutes:
            continue

        # Adds the room to the response.
        results.append(
            AvailabilityResponse(
                building_name=building.name,
                room_number=room.room_number,
                available_from=requested_time.strftime("%H:%M"),
                available_until=interval.end_time.strftime("%H:%M"),
                available_minutes=available_minutes,
            )
        )

    # Sorts results by building name and room number.
    results.sort(
        key=lambda result: (
            result.building_name,
            result.room_number,
        )
    )

    # Returns the available rooms.
    return results
