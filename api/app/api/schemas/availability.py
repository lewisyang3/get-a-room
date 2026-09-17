from pydantic import BaseModel


class AvailabilityResponse(BaseModel):
    building_name: str
    room_number: str
    available_from: str
    available_until: str
    available_minutes: int