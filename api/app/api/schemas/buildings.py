from pydantic import BaseModel, ConfigDict, Field


class BuildingResponse(BaseModel):
    """A building that availability searches."""

    building_id: int = Field(
        description="The building's id, usable as the `building_id` filter."
    )
    building_code: str = Field(
        description="The building's short code, usable as the `building_code` "
        "filter."
    )
    building_name: str = Field(description="The building's name.")
    latitude: float | None = Field(
        description="The building's latitude, or null when unknown."
    )
    longitude: float | None = Field(
        description="The building's longitude, or null when unknown."
    )


class BuildingList(BaseModel):
    """Every building that availability searches."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "results": [
                        {
                            "building_id": 2,
                            "building_code": "DWINELLE",
                            "building_name": "Dwinelle",
                            "latitude": 37.8705,
                            "longitude": -122.2606,
                        }
                    ]
                }
            ]
        }
    )

    results: list[BuildingResponse] = Field(description="Every building, by name.")
