from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.models import Building, ImportRun, ImportStatus, Meeting, Room, Term
from ingestion.report import build_report, format_report
from tests.api.conftest import add_room

MONDAY = 0
STARTED = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)


def add_run(
    db: Session,
    term: Term,
    status: ImportStatus,
    started_at: datetime = STARTED,
    rejection_counts: dict[str, int] | None = None,
) -> ImportRun:
    run = ImportRun(
        term_id=term.term_id,
        started_at=started_at,
        completed_at=started_at + timedelta(minutes=30),
        source_url=term.source_url,
        status=status,
        records_read=10,
        records_imported=4,
        records_rejected=6,
        records_failed=0,
        rejection_counts=rejection_counts,
    )
    db.add(run)
    db.flush()
    return run


def add_meeting(
    db: Session,
    term: Term,
    room: Room,
    source_record_id: str,
    start: time,
    end: time,
    meeting_type: str = "LEC",
    day_of_week: int = MONDAY,
) -> None:
    db.add(
        Meeting(
            room_id=room.room_id,
            term_id=term.term_id,
            day_of_week=day_of_week,
            start_time=start,
            end_time=end,
            meeting_type=meeting_type,
            source_record_id=source_record_id,
        )
    )
    db.flush()


def add_building(db: Session, name: str, **fields) -> Building:
    building = Building(name=name, short_code=name.upper().replace(" ", "-"), **fields)
    db.add(building)
    db.flush()
    return building


@pytest.fixture
def dwinelle(db: Session) -> Building:
    return add_building(db, "Dwinelle", latitude=37.87, longitude=-122.26)


def test_last_import_is_the_latest_completed_run(db: Session, term: Term):
    add_run(db, term, ImportStatus.COMPLETED)
    latest = add_run(
        db, term, ImportStatus.COMPLETED, started_at=STARTED + timedelta(days=1)
    )
    add_run(db, term, ImportStatus.FAILED, started_at=STARTED + timedelta(days=2))
    add_run(db, term, ImportStatus.FAILED, started_at=STARTED + timedelta(days=3))

    last = build_report(db, term).last_import

    assert last.run.import_id == latest.import_id
    assert last.failed_since == 2


def test_last_import_is_none_without_a_completed_run(db: Session, term: Term):
    add_run(db, term, ImportStatus.FAILED)

    assert build_report(db, term).last_import is None


def test_rejection_reasons_are_listed_most_common_first(db: Session, term: Term):
    add_run(
        db,
        term,
        ImportStatus.COMPLETED,
        rejection_counts={"online": 2, "section_type_not_room_occupying:IND": 4},
    )

    text = format_report(build_report(db, term))

    assert text.index("section_type_not_room_occupying:IND  4") < text.index(
        "online                               2"
    )


def test_a_run_from_before_reasons_were_recorded_says_so(db: Session, term: Term):
    add_run(db, term, ImportStatus.COMPLETED, rejection_counts=None)

    text = format_report(build_report(db, term))

    assert "Rejection reasons weren't recorded for this run." in text


def test_completion_time_is_shown_in_utc_whatever_the_session_zone(
    db: Session, term: Term
):
    add_run(db, term, ImportStatus.COMPLETED)
    db.execute(text("SET TIME ZONE 'America/Los_Angeles'"))
    db.expire_all()  # reload completed_at in the session's zone

    report = format_report(build_report(db, term))

    assert "completed 2026-10-05 07:30 UTC" in report


def test_coverage_counts(db: Session, term: Term, dwinelle: Building):
    unplaced = add_building(db, "Evans")
    add_building(db, "Uncovered", included_in_coverage=False)
    room = add_room(db, term, dwinelle, "242", {})
    add_room(db, term, unplaced, "10", {})
    add_meeting(db, term, room, "1", time(9, 0), time(10, 0), "LEC")
    add_meeting(db, term, room, "2", time(10, 0), time(11, 0), "DIS")
    add_meeting(db, term, room, "2", time(21, 0), time(23, 0), "DIS")
    add_meeting(db, term, room, "3", time(6, 30), time(8, 0), "LAB")

    coverage = build_report(db, term).coverage

    assert (coverage.buildings, coverage.covered_buildings) == (3, 2)
    # Only covered buildings matter: the uncovered one is never shown.
    assert coverage.without_coordinates == ["Evans"]
    assert (coverage.rooms, coverage.searchable_rooms) == (2, 2)
    assert (coverage.sections, coverage.meetings) == (3, 4)
    assert coverage.meetings_by_type == {"DIS": 2, "LAB": 1, "LEC": 1}
    assert coverage.outside_window == 2  # 21:00-23:00 and 06:30-08:00


def test_similar_room_numbers_in_one_building(
    db: Session, term: Term, dwinelle: Building
):
    evans = add_building(db, "Evans")
    for number in ["242", "0242", "B-4", "b4", "243"]:
        add_room(db, term, dwinelle, number, {})
    add_room(db, term, evans, "242", {})

    duplicates = build_report(db, term).duplicates

    assert sorted(duplicates.similar_rooms) == [
        "Dwinelle: 0242, 242",
        "Dwinelle: B-4, b4",
    ]


def test_similar_building_names(db: Session, term: Term, dwinelle: Building):
    add_building(db, "Dwinelle Hall")
    add_building(db, "Evans")

    assert build_report(db, term).duplicates.similar_buildings == [
        "Dwinelle, Dwinelle Hall"
    ]


def test_overlapping_sections_in_one_room(db: Session, term: Term, dwinelle: Building):
    room = add_room(db, term, dwinelle, "242", {})
    other_room = add_room(db, term, dwinelle, "243", {})
    add_meeting(db, term, room, "1", time(10, 0), time(12, 0))
    add_meeting(db, term, room, "2", time(11, 0), time(13, 0))  # overlaps 1
    add_meeting(db, term, room, "3", time(13, 0), time(14, 0))  # right after 2
    add_meeting(db, term, room, "1", time(11, 30), time(12, 30))  # 1's own block
    add_meeting(db, term, other_room, "4", time(10, 0), time(12, 0))
    add_meeting(db, term, room, "5", time(10, 0), time(12, 0), day_of_week=1)

    duplicates = build_report(db, term).duplicates

    # Section 1's two blocks each overlap section 2.
    assert duplicates.overlap_count == 2
    first = duplicates.overlap_examples[0]
    assert (first.building, first.room, first.day_of_week) == ("Dwinelle", "242", 0)
    assert first.first[0] == "1" and first.second[0] == "2"


def test_rooms_by_building_counts_rooms_in_use(
    db: Session, term: Term, dwinelle: Building
):
    empty = add_building(db, "Evans", included_in_coverage=False)
    add_room(db, term, dwinelle, "242", {})
    add_room(db, term, dwinelle, "243", {}).in_use = False
    db.flush()

    rows = build_report(db, term).rooms_by_building

    assert [(r.name, r.rooms, r.covered) for r in rows] == [
        ("Dwinelle", 1, True),
        (empty.name, 0, False),
    ]


def test_sample_availability_counts_searchable_rooms_free_then(
    db: Session, term: Term, dwinelle: Building
):
    uncovered = add_building(db, "Uncovered", included_in_coverage=False)
    add_room(db, term, dwinelle, "242", {MONDAY: [(time(7, 0), time(10, 0))]})
    add_room(db, term, dwinelle, "243", {MONDAY: [(time(10, 0), time(12, 0))]})
    add_room(db, term, uncovered, "1", {MONDAY: [(time(7, 0), time(22, 0))]})

    sample = build_report(db, term).sample

    # Half-open: 242 is booked from 10:00, 243 is free from 10:00.
    assert sample.free_counts[(MONDAY, time(10, 0))] == 1
    assert [(r.room, r.free_until) for r in sample.examples] == [("243", time(12, 0))]
