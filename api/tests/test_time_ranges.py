"""The generated `time_range` columns and the constraints built on them."""

from datetime import datetime, time, timezone

import pytest
from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import AvailabilityInterval, Building, Meeting, Room, Term


@pytest.fixture
def two_rooms(db: Session) -> tuple[Room, Room]:
    building = Building(name="Evans Hall", short_code="EVANS")
    first = Room(building=building, room_number="10")
    second = Room(building=building, room_number="20")
    db.add_all([building, first, second])
    db.flush()
    return first, second


def free(room: Room, term: Term, start: time, end: time) -> AvailabilityInterval:
    return AvailabilityInterval(
        room_id=room.room_id,
        term_id=term.term_id,
        day_of_week=0,
        start_time=start,
        end_time=end,
        computed_at=datetime.now(timezone.utc),
    )


def booked(room: Room, term: Term, source_record_id: str) -> Meeting:
    return Meeting(
        room_id=room.room_id,
        term_id=term.term_id,
        day_of_week=0,
        start_time=time(10, 0),
        end_time=time(11, 0),
        meeting_type="LEC",
        source_record_id=source_record_id,
    )


def test_time_range_is_generated_half_open(db, term, two_rooms):
    interval = free(two_rooms[0], term, time(9, 0), time(10, 30))
    db.add(interval)
    db.flush()

    assert (
        db.scalar(
            select(cast(AvailabilityInterval.time_range, String)).where(
                AvailabilityInterval.interval_id == interval.interval_id
            )
        )
        == "[09:00:00,10:30:00)"
    )


def test_overlapping_free_intervals_are_rejected(db, term, two_rooms):
    room = two_rooms[0]
    db.add_all(
        [
            free(room, term, time(9, 0), time(11, 0)),
            free(room, term, time(10, 0), time(12, 0)),
        ]
    )

    with pytest.raises(IntegrityError, match="ex_availability_interval_no_overlap"):
        db.flush()


def test_back_to_back_and_other_rooms_free_intervals_are_allowed(db, term, two_rooms):
    first, second = two_rooms
    db.add_all(
        [
            free(first, term, time(9, 0), time(10, 0)),
            # Starts as the previous one ends, so doesn't overlap it.
            free(first, term, time(10, 0), time(11, 0)),
            # Same times, different room.
            free(second, term, time(9, 0), time(10, 0)),
        ]
    )
    db.flush()

    assert db.scalar(select(func.count()).select_from(AvailabilityInterval)) == 3


def test_overlapping_meetings_in_one_room_are_allowed(db, term, two_rooms):
    # Cross-listed sections share a room and time; the report counts these.
    room = two_rooms[0]
    db.add_all([booked(room, term, "1"), booked(room, term, "2")])
    db.flush()

    assert db.scalar(select(func.count()).select_from(Meeting)) == 2
