from datetime import datetime, time, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.models import AvailabilityInterval, Building, Room, Term

FRIDAY = 4


def _add_building(
    db: Session,
    name: str,
    code: str,
    rooms: dict[str, bool],
    included_in_coverage: bool = True,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Building:
    """A building with rooms keyed by number, each mapped to `in_use`."""
    building = Building(
        name=name,
        short_code=code,
        included_in_coverage=included_in_coverage,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(building)
    db.flush()
    db.add_all(
        Room(building_id=building.building_id, room_number=number, in_use=in_use)
        for number, in_use in rooms.items()
    )
    db.commit()
    return building


def _results(client: TestClient) -> list[dict]:
    response = client.get("/buildings")
    assert response.status_code == 200, response.text
    return response.json()["results"]


def _names(client: TestClient) -> list[str]:
    return [building["building_name"] for building in _results(client)]


def test_returns_each_building_with_its_coordinates(client: TestClient, db: Session):
    dwinelle = _add_building(
        db,
        "Dwinelle",
        "DWINELLE",
        {"242": True},
        latitude=37.8705,
        longitude=-122.2606,
    )

    response = client.get("/buildings")

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "building_id": dwinelle.building_id,
                "building_code": "DWINELLE",
                "building_name": "Dwinelle",
                "latitude": 37.8705,
                "longitude": -122.2606,
            }
        ]
    }


def test_unknown_coordinates_are_null(client: TestClient, db: Session):
    _add_building(db, "Dwinelle", "DWINELLE", {"242": True})

    [building] = _results(client)

    assert (building["latitude"], building["longitude"]) == (None, None)


def test_buildings_outside_coverage_are_excluded(client: TestClient, db: Session):
    _add_building(db, "Dwinelle", "DWINELLE", {"242": True})
    _add_building(
        db, "Etcheverry", "ETCHEVERRY", {"3106": True}, included_in_coverage=False
    )

    assert _names(client) == ["Dwinelle"]


def test_buildings_with_no_rooms_in_use_are_excluded(client: TestClient, db: Session):
    _add_building(db, "Dwinelle", "DWINELLE", {"242": True})
    _add_building(db, "Etcheverry", "ETCHEVERRY", {"3106": False, "3107": False})

    assert _names(client) == ["Dwinelle"]


def test_buildings_with_no_rooms_are_excluded(client: TestClient, db: Session):
    _add_building(db, "Dwinelle", "DWINELLE", {"242": True})
    _add_building(db, "Etcheverry", "ETCHEVERRY", {})

    assert _names(client) == ["Dwinelle"]


def test_a_building_with_several_rooms_is_listed_once(client: TestClient, db: Session):
    _add_building(db, "Dwinelle", "DWINELLE", {"109": True, "242": True, "B4": False})

    assert _names(client) == ["Dwinelle"]


def test_buildings_are_sorted_by_name_then_id(client: TestClient, db: Session):
    etcheverry = _add_building(db, "Etcheverry", "ETCHEVERRY", {"3106": True})
    annex_1 = _add_building(db, "Annex", "ANNEX1", {"1": True})
    annex_2 = _add_building(db, "Annex", "ANNEX2", {"1": True})

    assert [b["building_id"] for b in _results(client)] == [
        annex_1.building_id,
        annex_2.building_id,
        etcheverry.building_id,
    ]


def test_no_buildings_returns_an_empty_list(client: TestClient):
    response = client.get("/buildings")

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_a_building_needs_no_availability_to_be_listed(client: TestClient, db: Session):
    """Buildings aren't tied to a term, so no availability is needed."""
    _add_building(db, "Dwinelle", "DWINELLE", {"242": True})

    assert _names(client) == ["Dwinelle"]


def test_lists_exactly_the_buildings_availability_can_return(
    client: TestClient, db: Session, term: Term
):
    """Fails if /buildings and /availability disagree on which buildings
    exist or on the fields that identify them."""
    _add_building(db, "Dwinelle", "DWINELLE", {"109": True, "B4": False})
    _add_building(db, "Evans", "EVANS", {"60": True})
    _add_building(db, "Cory", "CORY", {"241": True}, included_in_coverage=False)
    _add_building(db, "Etcheverry", "ETCHEVERRY", {"3106": False})
    _add_building(db, "Annex", "ANNEX", {})
    # Every room is free all day, so only the room and building rules decide.
    for room in db.query(Room).all():
        db.add(
            AvailabilityInterval(
                room_id=room.room_id,
                term_id=term.term_id,
                day_of_week=FRIDAY,
                start_time=time(7),
                end_time=time(22),
                computed_at=datetime.now(timezone.utc),
            )
        )
    db.commit()
    keys = ("building_id", "building_code", "building_name")

    available = client.get(
        "/availability",
        params={
            "term_id": term.term_id,
            "day_of_week": FRIDAY,
            "time": "10:00",
            "minimum_minutes": 1,
            "limit": 200,
        },
    )
    assert available.status_code == 200, available.text

    from_availability = {
        tuple(room[key] for key in keys) for room in available.json()["results"]
    }
    from_buildings = {tuple(b[key] for key in keys) for b in _results(client)}
    assert from_buildings == from_availability
    assert {name for _, _, name in from_buildings} == {"Dwinelle", "Evans"}
