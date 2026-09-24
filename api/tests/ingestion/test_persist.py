from datetime import time

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import (
    AvailabilityInterval,
    Building,
    ImportRun,
    ImportStatus,
    Meeting,
    Room,
    Term,
)
from app.models.availability.inversion import invert_intervals
from ingestion.fetch import FetchError
from ingestion.persist import (
    ImportAborted,
    _retire_stale_meetings,
    persist_section,
    run_import,
    taxonomy_term_id,
)
from ingestion.types import ParsedMeeting
from tests.ingestion.conftest import (
    FIXTURES,
    FakeResponse,
    FakeSession,
    listing_handler,
    make_section,
    persist_prior_sections,
)


def test_persist_section_creates_building_room_and_meeting(db: Session, term: Term):
    section = make_section()
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
    section = make_section()
    persist_section(db, term.term_id, section, seen=set())
    db.commit()
    first_id = (
        db.query(Meeting)
        .filter_by(source_record_id="1", day_of_week=0)
        .one()
        .meeting_id
    )

    persist_section(db, term.term_id, make_section(), seen=set())
    db.commit()

    meetings = db.query(Meeting).filter_by(source_record_id="1", day_of_week=0).all()
    assert len(meetings) == 1
    assert meetings[0].meeting_id == first_id


def test_persist_section_updates_changed_meeting_time(db: Session, term: Term):
    persist_section(db, term.term_id, make_section(), seen=set())
    db.commit()

    changed = make_section(
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
    persist_section(db, term.term_id, make_section(source_record_id="1"), seen=set())
    persist_section(db, term.term_id, make_section(source_record_id="2"), seen=set())
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
    same_day_twice = make_section(
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
        make_section(
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

    persist_section(db, term.term_id, make_section(), set())
    db.commit()

    meeting = db.query(Meeting).filter_by(source_record_id="1").one()
    assert (meeting.start_time, meeting.end_time) == (time(14, 0), time(15, 0))


def test_persist_section_removes_a_meeting_day_dropped_from_a_still_present_section(
    db: Session, term: Term
):
    two_days = make_section(
        meetings=[
            ParsedMeeting(day_of_week=0, start_time=time(14, 0), end_time=time(15, 0)),
            ParsedMeeting(day_of_week=2, start_time=time(14, 0), end_time=time(15, 0)),
        ]
    )
    persist_section(db, term.term_id, two_days, set())
    db.commit()
    assert db.query(Meeting).filter_by(source_record_id="1").count() == 2

    one_day = make_section(
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
    persist_section(db, term.term_id, make_section(source_record_id="1"), set())
    persist_section(db, term.term_id, make_section(source_record_id="2"), set())
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


def test_run_import_scrapes_the_terms_taxonomy_id_not_its_db_id(
    db: Session, term: Term
):
    """The DB's term_id and Berkeley's taxonomy id are unrelated numbers -
    the scrape must go by the term's source_url."""
    assert term.term_id != 8573
    session = FakeSession(_pipeline_handler)

    result = run_import(db, session, term.term_id, rate_limit_seconds=0)

    taxonomy_paths = {
        path for path, _ in session.calls if path.startswith("/taxonomy/term/")
    }
    assert taxonomy_paths == {"/taxonomy/term/8573"}
    assert result.source_url == term.source_url


@pytest.mark.parametrize(
    "source_url",
    [None, "https://classes.berkeley.edu/search/class", "https://x/taxonomy/term/85x"],
)
def test_run_import_rejects_a_term_without_a_usable_source_url(
    db: Session, term: Term, source_url: str | None
):
    term.source_url = source_url
    db.commit()
    session = FakeSession(_pipeline_handler)

    with pytest.raises(ValueError, match="source_url"):
        run_import(db, session, term.term_id, rate_limit_seconds=0)

    assert session.calls == []
    assert db.query(ImportRun).count() == 0


def test_run_import_rejects_a_missing_term(db: Session):
    with pytest.raises(ValueError, match="does not exist"):
        run_import(db, FakeSession(_pipeline_handler), 999_999, rate_limit_seconds=0)

    assert db.query(ImportRun).count() == 0


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
            rate_limit_seconds=0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    # The pipeline did accept a section before the enumeration failure...
    assert import_run.records_read == 1
    # ...but the rollback means nothing was actually persisted.
    assert import_run.records_imported == 0
    assert db.query(Meeting).count() == 0


def test_run_import_aborts_when_enumeration_returns_no_sections(
    db: Session, term: Term
):
    """An empty listing (site change, soft block) must not wipe the term."""
    persist_prior_sections(db, term, "a", "b")

    with pytest.raises(ImportAborted, match="no sections"):
        run_import(
            db,
            FakeSession(listing_handler()),
            term.term_id,
            rate_limit_seconds=0,
            max_retire_fraction=1.0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    assert {m.source_record_id for m in db.query(Meeting)} == {"a", "b"}


def test_run_import_aborts_when_every_section_is_rejected(db: Session, term: Term):
    """E.g. a parser regression rejecting everything: sections are read,
    none are seen, and retiring the whole term would trip the guard."""
    persist_prior_sections(db, term, "a", "b")

    with pytest.raises(ImportAborted, match="retire 2 of the term's 2"):
        run_import(
            db,
            FakeSession(listing_handler("ind-no-meetings")),
            term.term_id,
            rate_limit_seconds=0,
        )

    import_run = db.query(ImportRun).filter_by(term_id=term.term_id).one()
    assert import_run.status == ImportStatus.FAILED
    assert {m.source_record_id for m in db.query(Meeting)} == {"a", "b"}


def test_run_import_retires_sections_up_to_the_threshold(db: Session, term: Term):
    # lec_with_room.html is source_record_id "482493"; "gone" is half the term.
    persist_prior_sections(db, term, "482493", "gone")

    result = run_import(
        db,
        FakeSession(listing_handler("lec-with-room")),
        term.term_id,
        rate_limit_seconds=0,
    )

    assert result.status == ImportStatus.COMPLETED
    assert {m.source_record_id for m in db.query(Meeting)} == {"482493"}


def test_run_import_allows_a_full_retirement_when_explicitly_permitted(
    db: Session, term: Term
):
    persist_prior_sections(db, term, "a", "b")

    result = run_import(
        db,
        FakeSession(listing_handler("ind-no-meetings")),
        term.term_id,
        rate_limit_seconds=0,
        max_retire_fraction=1.0,
    )

    assert result.status == ImportStatus.COMPLETED
    assert db.query(Meeting).count() == 0


def test_run_import_rejects_an_invalid_max_retire_fraction(db: Session, term: Term):
    with pytest.raises(ValueError, match="max_retire_fraction"):
        run_import(
            db,
            FakeSession(listing_handler()),
            term.term_id,
            rate_limit_seconds=0,
            max_retire_fraction=1.5,
        )

    assert db.query(ImportRun).count() == 0


def test_building_short_code_does_not_collide_on_a_shared_long_prefix(
    db: Session, term: Term
):
    prefix = "A" * 55
    persist_section(
        db,
        term.term_id,
        make_section(building_name=f"{prefix} West", room_number="1"),
        set(),
    )
    persist_section(
        db,
        term.term_id,
        make_section(building_name=f"{prefix} East", room_number="1"),
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
    persist_section(db, term.term_id, make_section(source_record_id="old"), set())
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
        make_section(
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
    persist_section(db, term.term_id, make_section(source_record_id="prior"), set())
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
            make_section(source_record_id="1"),
            set(),
            building_cache,
            room_cache,
        )
        persist_section(
            db,
            term.term_id,
            make_section(source_record_id="2"),
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


def test_run_import_rejects_an_overlong_parser_version(db: Session, term: Term):
    session = FakeSession(listing_handler("lec-with-room"))

    with pytest.raises(ValueError, match="parser_version"):
        run_import(
            db, session, term.term_id, rate_limit_seconds=0, parser_version="x" * 51
        )

    assert session.calls == []
    assert db.query(ImportRun).count() == 0


def _fail_flush_when(db: Session, predicate) -> None:
    """Makes the next flush whose pending inserts match `predicate` raise."""

    def before_flush(session, flush_context, instances):
        if any(predicate(obj) for obj in session.new):
            event.remove(db, "before_flush", before_flush)
            raise RuntimeError("simulated database failure")

    event.listen(db, "before_flush", before_flush)


def test_run_import_records_a_failure_while_starting_the_run(db: Session, term: Term):
    """A failure writing the RUNNING row - before any scraping - must still
    be recorded, not escape with no ImportRun at all."""
    _fail_flush_when(
        db,
        lambda obj: isinstance(obj, ImportRun) and obj.status == ImportStatus.RUNNING,
    )

    with pytest.raises(RuntimeError, match="simulated") as exc_info:
        run_import(
            db,
            FakeSession(listing_handler("lec-with-room")),
            term.term_id,
            rate_limit_seconds=0,
        )

    [failed] = db.query(ImportRun).all()
    assert failed.status == ImportStatus.FAILED
    assert exc_info.value.import_run_id == failed.import_id


def test_run_import_records_an_interrupt_and_reraises_it(db: Session, term: Term):
    def interrupting(path: str, params: dict | None) -> FakeResponse:
        if path.startswith("/content/"):
            raise KeyboardInterrupt
        return listing_handler("lec-with-room")(path, params)

    with pytest.raises(KeyboardInterrupt) as exc_info:
        run_import(db, FakeSession(interrupting), term.term_id, rate_limit_seconds=0)

    [failed] = db.query(ImportRun).all()
    assert failed.status == ImportStatus.FAILED
    assert failed.error_message == "KeyboardInterrupt"
    assert exc_info.value.import_run_id == failed.import_id
    assert db.query(Meeting).count() == 0


def test_run_import_attaches_the_failed_run_id_to_the_exception(
    db: Session, term: Term
):
    with pytest.raises(ImportAborted) as exc_info:
        run_import(
            db, FakeSession(listing_handler()), term.term_id, rate_limit_seconds=0
        )

    [failed] = db.query(ImportRun).all()
    assert exc_info.value.import_run_id == failed.import_id


def test_run_import_reraises_the_original_error_if_recording_it_fails(
    db: Session, term: Term, caplog: pytest.LogCaptureFixture
):
    _fail_flush_when(
        db,
        lambda obj: isinstance(obj, ImportRun) and obj.status == ImportStatus.FAILED,
    )

    with pytest.raises(ImportAborted) as exc_info:
        run_import(
            db, FakeSession(listing_handler()), term.term_id, rate_limit_seconds=0
        )

    assert not hasattr(exc_info.value, "import_run_id")
    assert "could not record the FAILED ImportRun" in caplog.text
    assert db.query(ImportRun).count() == 0


@pytest.mark.parametrize(
    "source_url, expected",
    [
        ("https://classes.berkeley.edu/taxonomy/term/8573", 8573),
        ("https://classes.berkeley.edu/taxonomy/term/8573/", 8573),
        ("https://CLASSES.berkeley.edu/taxonomy/term/8573", 8573),
    ],
)
def test_taxonomy_term_id_accepts_the_canonical_url(source_url: str, expected: int):
    assert taxonomy_term_id(source_url) == expected


@pytest.mark.parametrize(
    "source_url",
    [
        None,
        "",
        "http://classes.berkeley.edu/taxonomy/term/8573",
        "https://evil.example/taxonomy/term/8573",
        "https://classes.berkeley.edu.evil.example/taxonomy/term/8573",
        "https://classes.berkeley.edu:8443/taxonomy/term/8573",
        "https://user@classes.berkeley.edu/taxonomy/term/8573",
        "https://classes.berkeley.edu/foo?next=/taxonomy/term/5",
        "https://classes.berkeley.edu/taxonomy/term/8573?page=2",
        "https://classes.berkeley.edu/taxonomy/term/8573#top",
        "https://classes.berkeley.edu/foo/taxonomy/term/8573",
        "https://classes.berkeley.edu/taxonomy/term/8573/extra",
        "https://classes.berkeley.edu/taxonomy/term/85x",
        "https://classes.berkeley.edu/taxonomy/term/\u0668\u0665",
        "https://[classes.berkeley.edu/taxonomy/term/8573",
    ],
)
def test_taxonomy_term_id_rejects_anything_else(source_url: str | None):
    with pytest.raises(ValueError, match="is not a https://classes.berkeley.edu"):
        taxonomy_term_id(source_url)


@pytest.mark.parametrize(
    "source_url",
    [
        "https://classes.berkeley.edu/taxonomy/term/85\n73",
        " https://classes.berkeley.edu/taxonomy/term/8573",
        "https://classes.berkeley.edu/taxonomy/term/8573\t",
        "\x01https://classes.berkeley.edu/taxonomy/term/8573",
        "https://classes.berkeley.edu/taxonomy/te\x7frm/8573",
        "https://classes.berkeley.edu/taxonomy/term/8573\u00a0",
    ],
)
def test_taxonomy_term_id_rejects_hidden_characters(source_url: str):
    """urlsplit strips or removes some of these, so they'd otherwise parse."""
    with pytest.raises(ValueError, match="whitespace or control characters"):
        taxonomy_term_id(source_url)


def test_reimport_frees_the_room_of_a_section_that_disappeared(db: Session, term: Term):
    """The stale pass deletes the vanished section's meetings, and the
    availability recomputed in the same run must not still see them."""
    run_import(
        db,
        FakeSession(listing_handler("lec-with-room", "dis-with-room")),
        term.term_id,
        rate_limit_seconds=0,
    )
    # lec_with_room.html: section 482493, Dwinelle 242, Fridays 14:00-17:00.
    room = (
        db.query(Room)
        .join(Building)
        .filter(Building.name == "Dwinelle", Room.room_number == "242")
        .one()
    )

    def friday_free_intervals() -> list[tuple[time, time]]:
        return [
            (interval.start_time, interval.end_time)
            for interval in db.query(AvailabilityInterval)
            .filter_by(term_id=term.term_id, room_id=room.room_id, day_of_week=4)
            .order_by(AvailabilityInterval.start_time)
        ]

    assert friday_free_intervals() == [
        (time(7, 0), time(14, 0)),
        (time(17, 0), time(22, 0)),
    ]

    # 482493 is gone from the listing; retiring 1 of 2 sections is allowed.
    result = run_import(
        db,
        FakeSession(listing_handler("dis-with-room")),
        term.term_id,
        rate_limit_seconds=0,
    )

    assert result.status == ImportStatus.COMPLETED
    assert db.query(Meeting).filter_by(source_record_id="482493").count() == 0
    assert friday_free_intervals() == [(time(7, 0), time(22, 0))]
