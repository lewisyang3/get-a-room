import hashlib
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Building, ImportRun, ImportStatus, Meeting, Room
from ingestion.fetch import SectionSession
from ingestion.filter import is_accepted
from ingestion.pipeline import IngestionPipeline
from ingestion.types import ParsedSection

logger = logging.getLogger(__name__)

# (source_record_id, day_of_week) is the identity a Meeting row is upserted
# and retired on within a given term - a section meeting on multiple days
# produces one Meeting row per day. Meeting's actual DB unique constraint is
# this pair alone (no term_id) - see the note in _upsert_meetings.
_MeetingKey = tuple[str, int]


def _building_short_code(name: str) -> str:
    """Derives a stable, unique key from a scraped building name.

    Berkeley's section pages don't expose a canonical building code (only
    free-text names like "Dwinelle Hall"), so this normalizes the name
    itself to serve as Building.short_code until a real code list is
    imported separately - see the "exact covered-building list" open
    decision in the project plan.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").upper()
    if len(slug) <= 50:
        return slug
    # Two distinct names sharing a 50-char prefix would otherwise collide
    # and silently merge into one Building row - a hash of the full slug
    # as a suffix keeps this key unique even when truncated.
    digest = hashlib.sha1(slug.encode()).hexdigest()[:8]
    return f"{slug[:41]}-{digest}"


# Per-run caches so repeated buildings/rooms across many sections (the
# common case - most sections share a building with earlier ones) cost one
# SELECT each instead of one per section.
_BuildingCache = dict[str, Building]
_RoomCache = dict[tuple[int, str], Room]


def _get_or_create_building(db: Session, name: str, cache: _BuildingCache) -> Building:
    short_code = _building_short_code(name)
    cached = cache.get(short_code)
    if cached is not None:
        return cached
    building = db.query(Building).filter_by(short_code=short_code).one_or_none()
    if building is None:
        building = Building(name=name, short_code=short_code)
        db.add(building)
        db.flush()
    cache[short_code] = building
    return building


def _get_or_create_room(
    db: Session, building: Building, room_number: str, cache: _RoomCache
) -> Room:
    key = (building.building_id, room_number)
    cached = cache.get(key)
    if cached is not None:
        return cached
    room = (
        db.query(Room)
        .filter_by(building_id=building.building_id, room_number=room_number)
        .one_or_none()
    )
    if room is None:
        room = Room(building_id=building.building_id, room_number=room_number)
        db.add(room)
        db.flush()
    cache[key] = room
    return room


def _upsert_meetings(
    db: Session,
    term_id: int,
    room: Room,
    section: ParsedSection,
    seen: set[_MeetingKey],
) -> None:
    for meeting_in in section.meetings:
        key = (section.source_record_id, meeting_in.day_of_week)
        seen.add(key)
        # Meeting's actual DB unique constraint is (source_record_id,
        # day_of_week) without term_id - scoping this lookup by term_id
        # anyway means a source_record_id reused across terms hits an
        # IntegrityError on insert instead of silently reassigning another
        # term's row to this one. That IntegrityError is caught by
        # run_import's try/except (not left uncaught) and turned into a
        # FAILED ImportRun.
        existing = (
            db.query(Meeting)
            .filter_by(
                source_record_id=section.source_record_id,
                day_of_week=meeting_in.day_of_week,
                term_id=term_id,
            )
            .one_or_none()
        )
        if existing is None:
            db.add(
                Meeting(
                    room_id=room.room_id,
                    term_id=term_id,
                    day_of_week=meeting_in.day_of_week,
                    start_time=meeting_in.start_time,
                    end_time=meeting_in.end_time,
                    meeting_type=section.section_type,
                    source_record_id=section.source_record_id,
                )
            )
            # A section can (rarely) have more than one meeting-details
            # block - see parse_section's docstring - which can produce two
            # ParsedMeetings for the same day. Without this flush, the next
            # iteration's lookup wouldn't see this insert (autoflush is
            # off) and would also take the insert branch, colliding on the
            # same (source_record_id, day_of_week) unique constraint.
            db.flush()
        else:
            # term_id isn't reassigned here - it's part of the lookup
            # filter above, so existing.term_id already equals term_id.
            existing.room_id = room.room_id
            existing.start_time = meeting_in.start_time
            existing.end_time = meeting_in.end_time
            existing.meeting_type = section.section_type


def persist_section(
    db: Session,
    term_id: int,
    section: ParsedSection,
    seen: set[_MeetingKey],
    building_cache: _BuildingCache | None = None,
    room_cache: _RoomCache | None = None,
) -> None:
    """Upserts an accepted section's meetings.

    Callers must only pass sections that have already been classified and
    accepted (see `ingestion.filter.is_accepted`) - a rejected section may
    lack a resolvable building/room and has nothing to persist.

    `building_cache`/`room_cache` are optional per-run caches (see
    `run_import`) - omitted, each call just hits the DB directly, which is
    fine for tests persisting a single section in isolation.
    """
    if building_cache is None:
        building_cache = {}
    if room_cache is None:
        room_cache = {}
    building = _get_or_create_building(db, section.building_name, building_cache)
    room = _get_or_create_room(db, building, section.room_number, room_cache)
    _upsert_meetings(db, term_id, room, section, seen)


def _retire_stale_meetings(db: Session, term_id: int, seen: set[_MeetingKey]) -> int:
    """Deletes this term's Meeting rows not touched by the current run.

    Only meaningful after a run completes enumeration successfully - `seen`
    is only a complete picture of "what's still scheduled" when nothing was
    missed.
    """
    stale = [
        meeting
        for meeting in db.query(Meeting).filter_by(term_id=term_id).all()
        if (meeting.source_record_id, meeting.day_of_week) not in seen
    ]
    for meeting in stale:
        db.delete(meeting)
    return len(stale)


def run_import(
    db: Session,
    session: SectionSession,
    term_id: int,
    source_url: str,
    *,
    rate_limit_seconds: float,
    max_pages: int = 5000,
    parser_version: str | None = None,
) -> ImportRun:
    """Runs the ingestion pipeline for a term and persists its output.

    Commits only happen once, at the very end - never mid-run - so a crash
    can't leave a half-written ImportRun row. On any failure, the session is
    rolled back (discarding this run's in-progress work entirely, including
    the not-yet-committed RUNNING ImportRun insert - a failed run persists
    nothing but a record of its own failure) and a fresh ImportRun row is
    inserted with status=FAILED, then the exception is re-raised: propagated,
    not swallowed, matching the pipeline's own enumeration-failure handling.

    Stale-meeting retirement only runs when the pipeline reports zero
    per-section failures this run - the pipeline swallows individual
    fetch/parse failures internally (they don't raise, just count against
    `pipeline.stats.failed`), so if any occurred, `seen` isn't a complete
    picture of what's still scheduled and treating an unseen Meeting as
    "gone" would risk deleting real availability data over a transient
    failure.
    """
    pipeline = IngestionPipeline(
        session, rate_limit_seconds=rate_limit_seconds, max_pages=max_pages
    )
    started_at = datetime.now(timezone.utc)
    import_run = ImportRun(
        term_id=term_id,
        started_at=started_at,
        source_url=source_url,
        parser_version=parser_version,
        status=ImportStatus.RUNNING,
    )
    db.add(import_run)
    db.flush()

    seen: set[_MeetingKey] = set()
    building_cache: _BuildingCache = {}
    room_cache: _RoomCache = {}
    try:
        for section in pipeline.run(term_id):
            if is_accepted(section):
                persist_section(db, term_id, section, seen, building_cache, room_cache)
        if pipeline.stats.failed:
            logger.warning(
                "import run for term %s: skipping stale-meeting retirement - "
                "%d section(s) failed to fetch/parse this run",
                term_id,
                pipeline.stats.failed,
            )
        else:
            _retire_stale_meetings(db, term_id, seen)

        # The commit itself can fail (e.g. a deferred IntegrityError from an
        # unflushed duplicate Meeting insert) - it must stay inside this
        # try block, or a failure here would propagate uncaught and leave
        # no FAILED ImportRun record at all.
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(timezone.utc)
        import_run.records_read = pipeline.stats.read
        import_run.records_imported = pipeline.stats.accepted
        import_run.records_rejected = pipeline.stats.rejected
        import_run.records_failed = pipeline.stats.failed
        db.commit()
    except Exception as exc:
        logger.exception("import run for term %s failed", term_id)
        db.rollback()
        failed_run = ImportRun(
            term_id=term_id,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            source_url=source_url,
            parser_version=parser_version,
            records_read=pipeline.stats.read,
            # Not pipeline.stats.accepted: db.rollback() above discarded
            # every upsert this run made, so the true persisted count is
            # always 0 here, regardless of how many sections were
            # classified as accepted before the failure.
            records_imported=0,
            records_rejected=pipeline.stats.rejected,
            records_failed=pipeline.stats.failed,
            status=ImportStatus.FAILED,
            error_message=str(exc)[:2000],
        )
        db.add(failed_run)
        db.commit()
        raise

    return import_run
