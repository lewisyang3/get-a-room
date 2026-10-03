from sqlalchemy import ColumnElement, and_

from app.models.models import Building, Room


# The rooms the API searches: in use, in a building inside the coverage
# area. /availability and /buildings both filter on this, so they agree on
# which buildings exist.
def searchable_rooms() -> ColumnElement[bool]:
    return and_(Room.in_use.is_(True), Building.included_in_coverage.is_(True))
