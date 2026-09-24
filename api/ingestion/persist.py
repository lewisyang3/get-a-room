import hashlib
import logging
import re
from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.models.models import Building, ImportRun, ImportStatus, Meeting, Room, Term
from ingestion.fetch import SectionSession
from ingestion.filter import is_accepted
from ingestion.pipeline import IngestionPipeline
from ingestion.types import ParsedSection

logger = logging.getLogger(__name__)

# A Meeting row's full identity within a term: one source record (section)
# can meet in more than one block on the same day, so day_of_week alone
# isn't unique - two same-day blocks (e.g. 14:00-15:00 and 16:00-17:00)
# are two distinct Meeting rows. Mirrors Meeting's DB unique constraint.
_MeetingKey = tuple[int, int, time, time]  # (room_id, day_of_week, start, end)

_TAXONOMY_TERM_RE = re.compile(r"/taxonomy/term/(\d+)/?(?:[?#]|$)")


def _taxonomy_term_id(source_url: str | None) -> int:
    """Extracts Berkeley's taxonomy term id from a Term's source_url.

    The database's Term.term_id and Berkeley's taxonomy id (e.g. 8573) are
    unrelated numbers - the scrape must always go by the latter.
    """
    match = _TAXONOMY_TERM_RE.search(source_url or "")
    if match is None:
        raise ValueError(
            f"term source_url {source_url!r} is not a classes.berkeley.edu "
            "/taxonomy/term/{id} URL"
        )
    return int(match.group(1))


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


def _sync_meetings(
    db: Session, term_id: int, room: Room, section: ParsedSection
) -> None:
    """Makes this term's Meeting rows for the section match `section.meetings`.

    A successfully parsed section is a complete picture of its own
    meetings, so it's reconciled as a set: rows still scheduled are kept
    (preserving their meeting_id), new ones are inserted, and ones no
    longer listed - a dropped day, a changed time - are deleted here
    rather than left to the run-wide stale pass (which is skipped when any
    other section fails this run).
    """
    existing: dict[_MeetingKey, Meeting] = {
        (m.room_id, m.day_of_week, m.start_time, m.end_time): m
        for m in db.query(Meeting).filter_by(
            term_id=term_id, source_record_id=section.source_record_id
        )
    }
    incoming: set[_MeetingKey] = {
        (room.room_id, m.day_of_week, m.start_time, m.end_time)
        for m in section.meetings
    }

    for key, meeting in existing.items():
        if key in incoming:
            meeting.meeting_type = section.section_type
        else:
            db.delete(meeting)

    for room_id, day_of_week, start_time, end_time in incoming - existing.keys():
        db.add(
            Meeting(
                room_id=room_id,
                term_id=term_id,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                meeting_type=section.section_type,
                source_record_id=section.source_record_id,
            )
        )
    # autoflush is off - flush so a later lookup in this run (e.g. the same
    # source_record_id reached via a second slug) sees these changes.
    db.flush()


def persist_section(
    db: Session,
    term_id: int,
    section: ParsedSection,
    seen: set[str],
    building_cache: _BuildingCache | None = None,
    room_cache: _RoomCache | None = None,
) -> None:
    """Upserts an accepted section's meetings and records it in `seen`.

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
    _sync_meetings(db, term_id, room, section)
    seen.add(section.source_record_id)


def _retire_stale_meetings(db: Session, term_id: int, seen: set[str]) -> int:
    """Deletes this term's Meeting rows whose section wasn't seen this run.

    Only meaningful after a run completes enumeration successfully - `seen`
    is only a complete picture of "what's still scheduled" when nothing was
    missed.
    """
    stale = [
        meeting
        for meeting in db.query(Meeting).filter_by(term_id=term_id).all()
        if meeting.source_record_id not in seen
    ]
    for meeting in stale:
        db.delete(meeting)
    return len(stale)


def run_import(
    db: Session,
    session: SectionSession,
    term_id: int,
    *,
    rate_limit_seconds: float,
    max_pages: int = 5000,
    parser_version: str | None = None,
) -> ImportRun:
    """Runs the ingestion pipeline for a term and persists its output.

    The sections scraped are the ones at the term's own `source_url` - a
    missing term or an unusable source_url raises before anything is
    written, including the ImportRun (it's a caller error, not a failed run).

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
    term = db.get(Term, term_id)
    if term is None:
        raise ValueError(f"term {term_id} does not exist")
    source_url = term.source_url
    taxonomy_term_id = _taxonomy_term_id(source_url)

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

    seen: set[str] = set()
    building_cache: _BuildingCache = {}
    room_cache: _RoomCache = {}
    try:
        for section in pipeline.run(taxonomy_term_id):
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
