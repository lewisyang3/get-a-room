"""Rooms, buildings, and a pinned clock shared by the availability tests."""

from collections.abc import Callable, Iterator
from datetime import datetime, time, timezone

import pytest
from sqlalchemy.orm import Session

from app.api.routes.availability import get_now
from app.main import app
from app.models.models import AvailabilityInterval, Building, Room, Term

THURSDAY, FRIDAY = 3, 4

# The `term` fixture is Fall 2025 (2025-08-27 to 2025-12-12), in
# America/Los_Angeles: PDT (UTC-7) until 2025-11-02, then PST (UTC-8).
FRIDAY_10AM_PDT = datetime(2025, 9, 5, 17, 0, tzinfo=timezone.utc)

EVANS = (37.87362, -122.25768)
DWINELLE = (37.87073, -122.26074)
# A point just outside Evans Hall.
NEAR_EVANS = {"near_latitude": 37.8736, "near_longitude": -122.2577}

Free = dict[int, list[tuple[time, time]]]


def add_room(
    db: Session, term: Term, building: Building, room_number: str, free: Free
) -> Room:
    room = Room(building_id=building.building_id, room_number=room_number)
    db.add(room)
    db.flush()
    for day_of_week, intervals in free.items():
        for start, end in intervals:
            db.add(
                AvailabilityInterval(
                    room_id=room.room_id,
                    term_id=term.term_id,
                    day_of_week=day_of_week,
                    start_time=start,
                    end_time=end,
                    computed_at=datetime.now(timezone.utc),
                )
            )
    return room


@pytest.fixture
def rooms(db: Session, term: Term) -> dict[str, Room]:
    dwinelle = Building(name="Dwinelle", short_code="DWINELLE")
    etcheverry = Building(name="Etcheverry", short_code="ETCHEVERRY")
    db.add_all([dwinelle, etcheverry])
    db.flush()
    created = {
        # Booked Fridays 14:00-17:00, free all of Thursday.
        "dwinelle_242": add_room(
            db,
            term,
            dwinelle,
            "242",
            {
                THURSDAY: [(time(7), time(22))],
                FRIDAY: [(time(7), time(14)), (time(17), time(22))],
            },
        ),
        # Free 60 minutes from Friday 10:00.
        "dwinelle_109": add_room(
            db, term, dwinelle, "109", {FRIDAY: [(time(7), time(11))]}
        ),
        # Free 59 minutes from Friday 10:00.
        "etcheverry_3106": add_room(
            db, term, etcheverry, "3106", {FRIDAY: [(time(7), time(10, 59))]}
        ),
    }
    db.commit()
    return created


@pytest.fixture
def clock() -> Iterator[Callable[[datetime], None]]:
    """Pins the endpoint's "now"; call it with an aware datetime."""

    def set_now(now: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: now

    yield set_now
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def located_rooms(db: Session, term: Term) -> None:
    """Rooms free all Friday in buildings with and without coordinates."""
    buildings = [
        Building(
            name="Dwinelle",
            short_code="DWINELLE",
            latitude=DWINELLE[0],
            longitude=DWINELLE[1],
        ),
        Building(
            name="Evans", short_code="EVANS", latitude=EVANS[0], longitude=EVANS[1]
        ),
        # The same distance as Evans, so their rooms must not interleave.
        Building(
            name="Evans Annex",
            short_code="EVANS-ANNEX",
            latitude=EVANS[0],
            longitude=EVANS[1],
        ),
        Building(name="Hearst Field Annex", short_code="HFA"),
    ]
    db.add_all(buildings)
    db.flush()
    dwinelle, evans, annex, hfa = buildings
    for building, numbers in [
        (dwinelle, ["109", "242"]),
        (evans, ["10", "11"]),
        (annex, ["1", "20"]),
        (hfa, ["B5"]),
    ]:
        for number in numbers:
            add_room(db, term, building, number, {FRIDAY: [(time(7), time(22))]})
    db.commit()
