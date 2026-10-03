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
    """One page of available rooms, with the weekday and time searched."""

    total: int
    limit: int
    offset: int
    day_of_week: int
    time: str
    results: list[AvailabilityResponse]
