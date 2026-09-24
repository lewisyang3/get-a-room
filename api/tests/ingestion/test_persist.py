from datetime import time
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import (
    Building,
    ImportRun,
    ImportStatus,
    Meeting,
    Room,
    Term,
)
from app.models.availability.inversion import invert_intervals
from ingestion.fetch import FetchError
from ingestion.persist import _retire_stale_meetings, persist_section, run_import
from ingestion.types import ParsedMeeting, ParsedSection
from tests.ingestion.conftest import FakeResponse, FakeSession

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sections"


def _section(
    source_record_id: str = "1",
    building_name: str = "Dwinelle Hall",
    room_number: str = "242",
    meetings: list[ParsedMeeting] | None = None,
    section_type: str = "LEC",
) -> ParsedSection:
    section = ParsedSection(
        source_record_id=source_record_id,
        slug=f"section-{source_record_id}",
        section_type=section_type,
        building_name=building_name,
        room_number=room_number,
        location_raw=f"{building_name} {room_number}",
        meetings=meetings
        if meetings is not None
        else [
            ParsedMeeting(day_of_week=0, start_time=time(14, 0), end_time=time(15, 0))
        ],
    )
    section.rejection_reason = None
    return section


def test_persist_section_creates_building_room_and_meeting(db: Session, term: Term):
    section = _section()
    persist_section(db, term.term_id, section, seen=set())
    db.commit()

    building = db.query(Building).filter_by(short_code="DWINELLE-HALL").one()
    room = (
        db.query(Room)
        .filter_by(building_id=building.building_id, room_number="242")
        .one()
    )
    meeting = db.query(Meeting).filter_by(source_record_id="1", day_of_week=0).one()

    assert building.name == "Dwinelle Hall"
    assert meeting.room_id == room.room_id
    assert meeting.term_id == term.term_id
    assert meeting.start_time == time(14, 0)
    assert meeting.end_time == time(15, 0)
    assert meeting.meeting_type == "LEC"


def test_persist_section_is_idempotent(db: Session, term: Term):
    section = _section()
    persist_section(db, term.term_id, section, seen=set())
    db.commit()
    first_id = (
        db.query(Meeting)
        .filter_by(source_record_id="1", day_of_week=0)
        .one()
        .meeting_id
    )

    persist_section(db, term.term_id, _section(), seen=set())
    db.commit()

    meetings = db.query(Meeting).filter_by(source_record_id="1", day_of_week=0).all()
    assert len(meetings) == 1
    assert meetings[0].meeting_id == first_id


def test_persist_section_updates_changed_meeting_time(db: Session, term: Term):
    persist_section(db, term.term_id, _section(), seen=set())
    db.commit()

    changed = _section(
        meetings=[
            ParsedMeeting(day_of_week=0, start_time=time(16, 0), end_time=time(17, 0))
        ]
    )
    persist_section(db, term.term_id, changed, seen=set())
    db.commit()

    meeting = db.query(Meeting).filter_by(source_record_id="1", day_of_week=0).one()
    assert meeting.start_time == time(16, 0)
    assert meeting.end_time == time(17, 0)


def test_persist_section_reuses_building_and_room_across_sections(
    db: Session, term: Term
):
    persist_section(db, term.term_id, _section(source_record_id="1"), seen=set())
    persist_section(db, term.term_id, _section(source_record_id="2"), seen=set())
    db.commit()

    assert db.query(Building).filter_by(short_code="DWINELLE-HALL").count() == 1
    assert db.query(Room).filter_by(room_number="242").count() == 1
    assert db.query(Meeting).count() == 2


def test_persist_section_keeps_both_meetings_on_the_same_day_within_one_section(
    db: Session, term: Term
):
    """A section with two meeting-details blocks landing on the same day
    (parse_section's docstring notes this is a rare but real case) must
    persist both blocks - keeping only one would make the other appear free."""
    same_day_twice = _section(
        meetings=[
            ParsedMeeting(day_of_week=0, start_time=time(14, 0), end_time=time(15, 0)),
            ParsedMeeting(day_of_week=0, start_time=time(16, 0), end_time=time(17, 0)),
        ]
    )
    persist_section(db, term.term_id, same_day_twice, set())
    db.commit()
    # Re-persisting the same section is still idempotent.
    persist_section(db, term.term_id, same_day_twice, set())
    db.commit()

    meetings = (
        db.query(Meeting)
        .filter_by(source_record_id="1", day_of_week=0)
        .order_by(Meeting.start_time)
        .all()
    )
    booked = [(m.start_time, m.end_time) for m in meetings]
    assert booked == [(time(14, 0), time(15, 0)), (time(16, 0), time(17, 0))]
    assert invert_intervals(booked) == [
        (time(7, 0), time(14, 0)),
        (time(15, 0), time(16, 0)),
        (time(17, 0), time(22, 0)),
    ]


def test_persist_section_drops_one_of_two_same_day_blocks(db: Session, term: Term):
    persist_section(
        db,
        term.term_id,
        _section(
            meetings=[
                ParsedMeeting(
                    day_of_week=0, start_time=time(14, 0), end_time=time(15, 0)
                ),
                ParsedMeeting(
                    day_of_week=0, start_time=time(16, 0), end_time=time(17, 0)
                ),
            ]
        ),
        set(),
    )
    db.commit()

    persist_section(db, term.term_id, _section(), set())
    db.commit()

    meeting = db.query(Meeting).filter_by(source_record_id="1").one()
    assert (meeting.start_time, meeting.end_time) == (time(14, 0), time(15, 0))


def test_persist_section_removes_a_meeting_day_dropped_from_a_still_present_section(
    db: Session, term: Term
):
    two_days = _section(
        meetings=[
            ParsedMeeting(day_of_week=0, start_time=time(14, 0), end_time=time(15, 0)),
            ParsedMeeting(day_of_week=2, start_time=time(14, 0), end_time=time(15, 0)),
        ]
    )
    persist_section(db, term.term_id, two_days, set())
    db.commit()
    assert db.query(Meeting).filter_by(source_record_id="1").count() == 2

    one_day = _section(
        meetings=[
            ParsedMeeting(day_of_week=0, start_time=time(14, 0), end_time=time(15, 0))
        ]
    )
    # No run-wide stale pass needed - the section itself is authoritative.
    persist_section(db, term.term_id, one_day, set())
    db.commit()

    remaining = db.query(Meeting).filter_by(source_record_id="1").all()
    assert [m.day_of_week for m in remaining] == [0]


def test_run_import_retires_a_section_that_disappears(db: Session, term: Term):
    persist_section(db, term.term_id, _section(source_record_id="1"), set())
    persist_section(db, term.term_id, _section(source_record_id="2"), set())
    db.commit()
    assert db.query(Meeting).count() == 2

    # Only section "1" is seen on this run - section "2" vanished.
    seen = {"1"}
    _retire_stale_meetings(db, term.term_id, seen)
    db.commit()

    remaining = db.query(Meeting).all()
    assert [m.source_record_id for m in remaining] == ["1"]


_TAXONOMY_PAGES = {
    0: (
        '<a href="/content/lec-with-room">A</a>'
        '<a href="/content/ind-no-meetings">B</a>'
    ),
    1: "",
}
_SECTION_HTML = {
    "/content/lec-with-room": (FIXTURES / "lec_with_room.html").read_text(),
    "/content/ind-no-meetings": (FIXTURES / "ind_no_meetings.html").read_text(),
}


def _pipeline_handler(path: str, params: dict | None) -> FakeResponse:
    if path.startswith("/taxonomy/term/"):
        page = (params or {}).get("page", 0)
        return FakeResponse(200, text=_TAXONOMY_PAGES.get(page, ""))
    if path in _SECTION_HTML:
        return FakeResponse(200, text=_SECTION_HTML[path])
    return FakeResponse(404)


def test_run_import_end_to_end(db: Session, term: Term):
    session = FakeSession(_pipeline_handler)

    result = run_import(
        db,
        session,
        term.term_id,
        source_url="https://classes.berkeley.edu/taxonomy/term/8573",
        rate_limit_seconds=0,
    )

    assert result.status == ImportStatus.COMPLETED
    assert result.records_read == 2
    assert result.records_imported == 1
    assert result.records_rejected == 1
    assert result.records_failed == 0
    assert result.completed_at is not None

    meeting = db.query(Meeting).filter_by(term_id=term.term_id).one()
    assert meeting.meeting_type == "LEC"


def test_run_import_records_enumeration_failure_and_reraises(db: Session, term: Term):
    def handler(path: str, params: dict | None) -> FakeResponse:
        assert path.startswith("/taxonomy/term/")
        return FakeResponse(403, text="Forbidden")

    session = FakeSession(handler)

    with pytest.raises(FetchError):
        run_import(
            db,
            session,
            term.term_id,
            source_url="https://classes.berkeley.edu/taxonomy/term/8573",
            rate_limit_seconds=0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    assert import_run.error_message is not None
    assert db.query(Meeting).count() == 0


def test_run_import_records_zero_imported_on_a_failure_after_partial_success(
    db: Session, term: Term
):
    """A section accepted before a later enumeration failure must not be
    counted as "imported" on the FAILED ImportRun - the rollback discards
    it, so the true persisted count is 0, not pipeline.stats.accepted."""

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            if page == 0:
                return FakeResponse(200, text='<a href="/content/lec-with-room">A</a>')
            return FakeResponse(403, text="Forbidden")
        return FakeResponse(200, text=(FIXTURES / "lec_with_room.html").read_text())

    with pytest.raises(FetchError):
        run_import(
            db,
            FakeSession(handler),
            term.term_id,
            source_url="https://classes.berkeley.edu/taxonomy/term/8573",
            rate_limit_seconds=0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    # The pipeline did accept a section before the enumeration failure...
    assert import_run.records_read == 1
    # ...but the rollback means nothing was actually persisted.
    assert import_run.records_imported == 0
    assert db.query(Meeting).count() == 0


def test_building_short_code_does_not_collide_on_a_shared_long_prefix(
    db: Session, term: Term
):
    prefix = "A" * 55
    persist_section(
        db,
        term.term_id,
        _section(building_name=f"{prefix} West", room_number="1"),
        set(),
    )
    persist_section(
        db,
        term.term_id,
        _section(building_name=f"{prefix} East", room_number="1"),
        set(),
    )
    db.commit()

    buildings = db.query(Building).all()
    assert len(buildings) == 2
    assert len({b.short_code for b in buildings}) == 2
    assert all(len(b.short_code) <= 50 for b in buildings)


def test_run_import_skips_stale_retirement_when_a_section_fails(
    db: Session, term: Term
):
    """A section that 404s this run must not cause an unrelated, still-real
    Meeting from a prior run to be deleted as "stale"."""
    persist_section(db, term.term_id, _section(source_record_id="old"), set())
    db.commit()

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            pages = {0: '<a href="/content/broken">A</a>', 1: ""}
            return FakeResponse(200, text=pages.get(page, ""))
        return FakeResponse(404)

    result = run_import(
        db,
        FakeSession(handler),
        term.term_id,
        source_url="https://classes.berkeley.edu/taxonomy/term/8573",
        rate_limit_seconds=0,
    )

    assert result.status == ImportStatus.COMPLETED
    assert result.records_failed == 1
    # The prior run's meeting must survive - it wasn't "seen" this run only
    # because a fetch failed, not because the class actually disappeared.
    assert db.query(Meeting).filter_by(source_record_id="old").count() == 1


def test_run_import_applies_a_changed_section_even_when_another_section_fails(
    db: Session, term: Term
):
    """A section that parses fine this run is reconciled on its own, so a
    changed meeting time isn't left stale just because some other section
    failed and the run-wide stale pass was skipped."""
    # lec_with_room.html parses to source_record_id "482493", Friday.
    persist_section(
        db,
        term.term_id,
        _section(
            source_record_id="482493",
            meetings=[
                ParsedMeeting(day_of_week=4, start_time=time(7, 0), end_time=time(8, 0))
            ],
        ),
        set(),
    )
    db.commit()

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            pages = {
                0: '<a href="/content/lec-with-room">A</a><a href="/content/broken">B</a>',
                1: "",
            }
            return FakeResponse(200, text=pages.get(page, ""))
        if path == "/content/lec-with-room":
            return FakeResponse(200, text=(FIXTURES / "lec_with_room.html").read_text())
        return FakeResponse(404)

    result = run_import(
        db,
        FakeSession(handler),
        term.term_id,
        source_url="https://classes.berkeley.edu/taxonomy/term/8573",
        rate_limit_seconds=0,
    )

    assert result.records_failed == 1
    meetings = db.query(Meeting).filter_by(source_record_id="482493").all()
    assert len(meetings) == 1
    assert meetings[0].start_time != time(7, 0)


def test_run_import_marks_failed_without_pending_rollback_error(
    db: Session, term: Term, monkeypatch: pytest.MonkeyPatch
):
    """An IntegrityError mid-run must still leave the ImportRun FAILED, not
    stuck RUNNING or masked by a PendingRollbackError from committing a
    poisoned session."""
    persist_section(db, term.term_id, _section(source_record_id="prior"), set())
    db.commit()

    def violate_check_constraint(db, term_id, section, *args):
        db.add(
            Meeting(
                room_id=db.query(Room).first().room_id,
                term_id=term_id,
                day_of_week=9,
                start_time=time(9, 0),
                end_time=time(10, 0),
                meeting_type="LEC",
                source_record_id=section.source_record_id,
            )
        )
        db.flush()

    monkeypatch.setattr("ingestion.persist.persist_section", violate_check_constraint)

    def handler(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/taxonomy/term/"):
            page = (params or {}).get("page", 0)
            pages = {0: '<a href="/content/lec-with-room">A</a>', 1: ""}
            return FakeResponse(200, text=pages.get(page, ""))
        return FakeResponse(200, text=(FIXTURES / "lec_with_room.html").read_text())

    with pytest.raises(IntegrityError):
        run_import(
            db,
            FakeSession(handler),
            term.term_id,
            source_url="https://classes.berkeley.edu/taxonomy/term/8573",
            rate_limit_seconds=0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    assert import_run.completed_at is not None
    # The prior committed meeting survives; nothing from the failed run does.
    assert [m.source_record_id for m in db.query(Meeting).all()] == ["prior"]


def test_persist_section_caches_building_and_room_lookups_within_a_run(
    db: Session, term: Term
):
    """Two sections sharing a building/room must only SELECT each once."""
    queries: list[str] = []

    def _count(conn, cursor, statement, *args):
        lowered = statement.lower()
        if lowered.strip().startswith("select") and (
            "from building" in lowered or "from room" in lowered
        ):
            queries.append(lowered)

    event.listen(db.get_bind(), "before_cursor_execute", _count)
    try:
        building_cache: dict = {}
        room_cache: dict = {}
        persist_section(
            db,
            term.term_id,
            _section(source_record_id="1"),
            set(),
            building_cache,
            room_cache,
        )
        persist_section(
            db,
            term.term_id,
            _section(source_record_id="2"),
            set(),
            building_cache,
            room_cache,
        )
        db.commit()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _count)

    building_queries = [q for q in queries if "from building" in q]
    room_queries = [q for q in queries if "from room" in q]
    assert len(building_queries) == 1
    assert len(room_queries) == 1
