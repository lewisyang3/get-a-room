from datetime import date, datetime, time, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models.availability.recompute import recompute_availability
from app.models.models import (
    AvailabilityInterval,
    Building,
    Meeting,
    Room,
    Term,
)


def test_recompute_availability_rebuilds_room_intervals():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        term = Term(
            name="Fall 2026",
            start_date=date(2026, 8, 17),
            end_date=date(2026, 12, 18),
        )
        building = Building(name="Engineering", short_code="ENG")
        room = Room(building=building, room_number="101")
        db.add_all([term, building, room])
        db.flush()

        db.add(
            Meeting(
                room_id=room.room_id,
                term_id=term.term_id,
                day_of_week=0,
                start_time=time(10, 0),
                end_time=time(11, 0),
                meeting_type="class",
                source_record_id="section-1",
            )
        )
        db.commit()

        count = recompute_availability(
            db,
            term.term_id,
            source_version="test",
            computed_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        db.commit()

        intervals = db.scalars(
            select(AvailabilityInterval)
            .where(AvailabilityInterval.term_id == term.term_id)
            .order_by(
                AvailabilityInterval.day_of_week,
                AvailabilityInterval.start_time,
            )
        ).all()

    assert count == 8
    assert [(row.start_time, row.end_time) for row in intervals[:2]] == [
        (time(7, 0), time(10, 0)),
        (time(11, 0), time(22, 0)),
    ]
    assert all(row.source_version == "test" for row in intervals)
    assert all(
        row.computed_at.replace(tzinfo=timezone.utc)
        == datetime(2026, 8, 1, tzinfo=timezone.utc)
        for row in intervals
    )
    assert len(intervals) == 8
