from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.models import Building, ImportStatus, Room, Term
from ingestion.persist import run_import
from tests.conftest import FakeSession, listing_handler

FRIDAY = 4


@pytest.fixture
def imported_term(db: Session, term: Term) -> Term:
    # lec_with_room.html: Dwinelle 242, Fridays 14:00-17:00.
    # dis_with_room.html: Valley Life Sciences 3030, Wednesdays 12:00-13:00.
    result = run_import(
        db,
        FakeSession(listing_handler("lec-with-room", "dis-with-room")),
        term.term_id,
        rate_limit_seconds=0,
    )
    assert result.status == ImportStatus.COMPLETED
    return term


def _available(
    client: TestClient, term_id: int, at: str, day_of_week: int = FRIDAY
) -> dict[tuple[str, str], dict]:
    response = client.get(
        "/availability",
        params={"term_id": term_id, "day_of_week": day_of_week, "time": at},
    )
    assert response.status_code == 200
    return {
        (r["building_name"], r["room_number"]): r for r in response.json()["results"]
    }


def test_an_imported_room_is_available_until_its_next_meeting(
    client: TestClient, db: Session, imported_term: Term
):
    rooms = _available(client, imported_term.term_id, "10:00")

    room = (
        db.query(Room)
        .join(Building)
        .filter(Building.name == "Dwinelle", Room.room_number == "242")
        .one()
    )
    assert rooms[("Dwinelle", "242")] == {
        "room_id": room.room_id,
        "building_id": room.building_id,
        "building_code": "DWINELLE",
        "building_name": "Dwinelle",
        "room_number": "242",
        "available_from": "10:00",
        "available_until": "14:00",
        "available_minutes": 240,
        "distance_meters": None,
    }
    assert rooms[("Valley Life Sciences", "3030")]["available_until"] == "22:00"


def test_an_imported_room_is_not_available_during_its_meeting(
    client: TestClient, imported_term: Term
):
    rooms = _available(client, imported_term.term_id, "15:00")

    assert ("Dwinelle", "242") not in rooms
    assert ("Valley Life Sciences", "3030") in rooms


def test_an_imported_room_is_available_from_the_moment_its_meeting_ends(
    client: TestClient, imported_term: Term
):
    """Meetings end exclusively: [14:00, 17:00) leaves the room free at 17:00."""
    rooms = _available(client, imported_term.term_id, "17:00")

    assert rooms[("Dwinelle", "242")]["available_until"] == "22:00"
    assert rooms[("Dwinelle", "242")]["available_minutes"] == 300


def test_another_terms_availability_is_empty(
    client: TestClient, db: Session, imported_term: Term
):
    other_term = Term(
        name="Spring 2026",
        start_date=date(2026, 1, 20),
        end_date=date(2026, 5, 15),
        source_url="https://classes.berkeley.edu/taxonomy/term/8600",
    )
    db.add(other_term)
    db.commit()

    assert _available(client, other_term.term_id, "10:00") == {}
