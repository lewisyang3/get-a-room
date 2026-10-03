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
