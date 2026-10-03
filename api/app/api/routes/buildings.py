from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.queries import searchable_rooms
from app.api.schemas.buildings import BuildingList, BuildingResponse
from app.db import get_db
from app.models.models import Building, Room

# Creates a router for building-related endpoints.
router = APIRouter(
    prefix="/buildings",
    tags=["buildings"],
)


# Returns every building that availability searches.
@router.get("", response_model=BuildingList, summary="List buildings")
def list_buildings(
    # Gets a database session from FastAPI.
    db: Session = Depends(get_db),
) -> BuildingList:
    """The buildings `/availability` searches: those inside the coverage area
    with at least one room in use, sorted by name. A listed building can still
    have no free room at a given time. Use a building's `building_id` or
    `building_code` as the `/availability` filter of the same name.
    """
    # Keeps buildings with a searchable room, listing each once; the id
    # breaks ties between buildings with the same name.
    statement = (
        select(Building)
        .join(Room, Room.building_id == Building.building_id)
        .where(searchable_rooms())
        .distinct()
        .order_by(Building.name, Building.building_id)
    )

    return BuildingList(
        results=[
            BuildingResponse(
                building_id=building.building_id,
                building_code=building.short_code,
                building_name=building.name,
                latitude=building.latitude,
                longitude=building.longitude,
            )
            for building in db.scalars(statement)
        ]
    )
