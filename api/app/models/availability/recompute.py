from collections import defaultdict
from datetime import datetime, time, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.availability.inversion import invert_intervals
from app.models.models import AvailabilityInterval, Meeting, Room


def recompute_availability(
    db: Session,
    term_id: int,
    *,
    source_version: str | None = None,
    computed_at: datetime | None = None,
    day_start: time = time(7, 0),
    day_end: time = time(22, 0),
) -> int:
    """Rebuild availability intervals for every room in a term.

    Existing intervals for the term are replaced in the current transaction.
    The caller is responsible for committing or rolling back the transaction.
    Returns the number of intervals inserted.
    """
    meetings = db.scalars(
        select(Meeting).where(Meeting.term_id == term_id)
    ).all()
    room_ids = db.scalars(select(Room.room_id).order_by(Room.room_id)).all()

    booked_by_room_day: dict[tuple[int, int], list[tuple[time, time]]] = defaultdict(list)
    for meeting in meetings:
        booked_by_room_day[(meeting.room_id, meeting.day_of_week)].append(
            (meeting.start_time, meeting.end_time)
        )

    db.execute(
        delete(AvailabilityInterval).where(
            AvailabilityInterval.term_id == term_id
        )
    )

    timestamp = computed_at or datetime.now(timezone.utc)
    intervals: list[AvailabilityInterval] = []

    for room_id in room_ids:
        for day_of_week in range(7):
            free_intervals = invert_intervals(
                booked_by_room_day[(room_id, day_of_week)],
                day_start=day_start,
                day_end=day_end,
            )
            intervals.extend(
                AvailabilityInterval(
                    room_id=room_id,
                    term_id=term_id,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    source_version=source_version,
                    computed_at=timestamp,
                )
                for start_time, end_time in free_intervals
            )

    db.add_all(intervals)
    db.flush()
    return len(intervals)
