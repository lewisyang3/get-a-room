from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityResponse(BaseModel):
    """A room with no scheduled class at the time searched."""

    room_id: int = Field(description="The room's id.")
    building_id: int = Field(description="The room's building's id.")
    building_code: str = Field(
        description="The building's short code, usable as the `building_code` "
        "filter."
    )
    building_name: str = Field(description="The building's name.")
    room_number: str = Field(description="The room number within the building.")
    available_from: str = Field(
        description="The time searched, `HH:MM` in the term's timezone."
    )
    available_until: str = Field(
        description="When the room's next class starts, or 22:00 if none does, "
        "`HH:MM` in the term's timezone."
    )
    available_minutes: int = Field(
        description="Whole minutes from `available_from` to `available_until`."
    )


class AvailabilityPage(BaseModel):
    """One page of available rooms, with the date, weekday, and time searched."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 42,
                    "limit": 50,
                    "offset": 0,
                    "date": "2025-10-17",
                    "day_of_week": 4,
                    "time": "14:30",
                    "results": [
                        {
                            "room_id": 7,
                            "building_id": 2,
                            "building_code": "DWINELLE",
                            "building_name": "Dwinelle",
                            "room_number": "242",
                            "available_from": "14:30",
                            "available_until": "17:00",
                            "available_minutes": 150,
                        }
                    ],
                }
            ]
        }
    )

    total: int = Field(description="Rooms matching the search, across all pages.")
    limit: int = Field(description="The page size requested.")
    offset: int = Field(description="Rooms skipped before this page.")
    date: Date | None = Field(
        description="The local date searched; null for a `day_of_week` + `time` "
        "search, which covers every week."
    )
    day_of_week: int = Field(description="The weekday searched, 0 = Monday.")
    time: str = Field(description="The time searched, `HH:MM` in the term's timezone.")
    results: list[AvailabilityResponse] = Field(
        description="This page of rooms, by building name, then room number."
    )
