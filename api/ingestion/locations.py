"""Building coordinates from a curated CSV.

Berkeley's section pages don't give building coordinates, so they're kept by
hand in data/building_locations.csv (name,latitude,longitude) and applied with
`python -m ingestion.cli buildings set-locations`.
"""

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Building
from ingestion.persist import building_short_code

DEFAULT_LOCATIONS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "building_locations.csv"
)

_COLUMNS = ("name", "latitude", "longitude")


@dataclass(frozen=True)
class BuildingLocation:
    name: str
    latitude: float
    longitude: float


@dataclass
class LocationSummary:
    """What applying the locations changed."""

    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    # CSV names with no building in the database.
    unmatched: list[str] = field(default_factory=list)
    # Covered buildings that still have no coordinates.
    missing: list[str] = field(default_factory=list)


def _coordinate(value: str, line: int, column: str, limit: float) -> float:
    try:
        number = float(value)
    except ValueError:
        number = math.nan
    if not -limit <= number <= limit:
        raise ValueError(
            f"line {line}: {column} must be a number from {-limit:g} to "
            f"{limit:g}, got {value!r}"
        )
    return number


def load_locations(path: Path) -> list[BuildingLocation]:
    """Reads and validates the CSV. Raises ValueError naming the line at
    fault, and OSError if the file can't be read."""
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != _COLUMNS:
            raise ValueError(
                f"line 1: expected the header {','.join(_COLUMNS)}, got "
                f"{','.join(reader.fieldnames or ())!r}"
            )
        locations: list[BuildingLocation] = []
        # Names that key to the same building would silently overwrite
        # each other.
        seen: dict[str, int] = {}
        for row in reader:
            line = reader.line_num
            if None in row.values() or None in row:
                raise ValueError(f"line {line}: expected {len(_COLUMNS)} columns")
            name = row["name"].strip()
            if not name:
                raise ValueError(f"line {line}: name is blank")
            key = building_short_code(name)
            if key in seen:
                raise ValueError(
                    f"line {line}: {name!r} is the same building as line {seen[key]}"
                )
            seen[key] = line
            locations.append(
                BuildingLocation(
                    name=name,
                    latitude=_coordinate(row["latitude"], line, "latitude", 90),
                    longitude=_coordinate(row["longitude"], line, "longitude", 180),
                )
            )
    return locations


def apply_locations(db: Session, locations: list[BuildingLocation]) -> LocationSummary:
    """Sets coordinates on the buildings the CSV names, matching names the
    same way imports key buildings. Doesn't commit."""
    summary = LocationSummary()
    buildings = {
        building.short_code: building for building in db.scalars(select(Building))
    }
    for location in locations:
        building = buildings.get(building_short_code(location.name))
        if building is None:
            summary.unmatched.append(location.name)
            continue
        coordinates = (location.latitude, location.longitude)
        if (building.latitude, building.longitude) == coordinates:
            summary.unchanged.append(building.name)
            continue
        building.latitude, building.longitude = coordinates
        summary.updated.append(building.name)
    summary.missing = sorted(
        building.name
        for building in buildings.values()
        if building.included_in_coverage
        and (building.latitude is None or building.longitude is None)
    )
    return summary
