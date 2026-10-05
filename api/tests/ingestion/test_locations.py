from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.models import Building
from ingestion.locations import (
    DEFAULT_LOCATIONS_PATH,
    BuildingLocation,
    apply_locations,
    load_locations,
)
from ingestion.persist import building_short_code


def _csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "locations.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _building(db: Session, name: str, **fields) -> Building:
    building = Building(name=name, short_code=building_short_code(name), **fields)
    db.add(building)
    db.commit()
    return building


def test_load_locations_reads_each_row(tmp_path: Path):
    path = _csv(
        tmp_path,
        "name,latitude,longitude\n"
        " Dwinelle ,37.87073,-122.26074\n"
        "Evans,37.87362,-122.25768\n",
    )

    assert load_locations(path) == [
        BuildingLocation("Dwinelle", 37.87073, -122.26074),
        BuildingLocation("Evans", 37.87362, -122.25768),
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("name,lat,lng\nEvans,1,2\n", "line 1: expected the header"),
        ("", "line 1: expected the header"),
        ("name,latitude,longitude\nEvans,1\n", "line 2: expected 3 columns"),
        ("name,latitude,longitude\nEvans,1,2,3\n", "line 2: expected 3 columns"),
        ("name,latitude,longitude\n ,1,2\n", "line 2: name is blank"),
        ("name,latitude,longitude\nEvans,north,2\n", "line 2: latitude must be"),
        ("name,latitude,longitude\nEvans,91,2\n", "line 2: latitude must be"),
        ("name,latitude,longitude\nEvans,1,-180.5\n", "line 2: longitude must be"),
        ("name,latitude,longitude\nEvans,nan,2\n", "line 2: latitude must be"),
        (
            "name,latitude,longitude\nEvans,1,2\nevans ,3,4\n",
            "line 3: 'evans' is the same building as line 2",
        ),
    ],
)
def test_load_locations_rejects_an_invalid_file(tmp_path: Path, text, message):
    with pytest.raises(ValueError, match=message):
        load_locations(_csv(tmp_path, text))


def test_the_repo_csv_is_valid():
    locations = load_locations(DEFAULT_LOCATIONS_PATH)

    names = {location.name for location in locations}
    assert {"Dwinelle", "Evans"} <= names
    # Every building is on the Berkeley campus or next to it.
    for location in locations:
        assert 37.86 < location.latitude < 37.88, location
        assert -122.27 < location.longitude < -122.25, location


def test_apply_locations_matches_names_like_imports_do(db: Session):
    dwinelle = _building(db, "Dwinelle")
    evans = _building(db, "Evans", latitude=37.87362, longitude=-122.25768)
    wheeler = _building(db, "Wheeler")
    _building(db, "Closed Hall", included_in_coverage=False)

    summary = apply_locations(
        db,
        [
            BuildingLocation("dwinelle", 37.87073, -122.26074),
            BuildingLocation("Evans", 37.87362, -122.25768),
            BuildingLocation("Soda", 37.87562, -122.25871),
        ],
    )
    db.commit()

    assert (dwinelle.latitude, dwinelle.longitude) == (37.87073, -122.26074)
    assert summary.updated == ["Dwinelle"]
    assert summary.unchanged == ["Evans"]
    assert summary.unmatched == ["Soda"]
    # Buildings left out of coverage aren't searched, so they don't count.
    assert summary.missing == ["Wheeler"]
    assert (wheeler.latitude, wheeler.longitude) == (None, None)
    assert evans.latitude == 37.87362
