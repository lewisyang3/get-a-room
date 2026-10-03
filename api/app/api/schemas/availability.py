from datetime import date as Date

from pydantic import BaseModel


class AvailabilityResponse(BaseModel):
    room_id: int
    building_id: int
    building_code: str
    building_name: str
    room_number: str
    available_from: str
    available_until: str
    available_minutes: int


class AvailabilityPage(BaseModel):
    """One page of available rooms, with the date, weekday, and time searched."""

    total: int
    limit: int
    offset: int
    # The local date searched; None for a weekday-and-time search.
    date: Date | None
    day_of_week: int
    time: str
    results: list[AvailabilityResponse]
