import hashlib
import logging
import re
from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.models.models import Building, ImportRun, ImportStatus, Meeting, Room
from ingestion.fetch import SectionSession
from ingestion.filter import is_accepted
from ingestion.pipeline import IngestionPipeline
from ingestion.types import ParsedSection

logger = logging.getLogger(__name__)

# A meeting block is unique within a term by source section, weekday, and
# start time. A section can have more than one block on the same weekday.
_MeetingKey = tuple[int, str, int, time]


def _building_short_code(name: str) -> str:
    """Derive a stable, unique key from a scraped building name."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").upper()
    if len(slug) <= 50:
        return slug
    digest = hashlib.sha1(slug.encode()).hexdigest()[:8]
    return f"{slug[:41]}-{digest}"


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
        key = (
            term_id,
            section.source_record_id,
            meeting_in.day_of_week,
            meeting_in.start_time,
        )
        seen.add(key)
        existing = (
            db.query(Meeting)
            .filter_by(
                term_id=term_id,
                source_record_id=section.source_record_id,
                day_of_week=meeting_in.day_of_week,
                start_time=meeting_in.start_time,
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
            # The session disables autoflush, so flush before another block
            # from this section is looked up.
            db.flush()
        else:
            existing.room_id = room.room_id
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
    """Upsert an accepted section's meeting blocks."""
    if building_cache is None:
        building_cache = {}
    if room_cache is None:
        room_cache = {}

    building = _get_or_create_building(db, section.building_name, building_cache)
    room = _get_or_create_room(db, building, section.room_number, room_cache)
    _upsert_meetings(db, term_id, room, section, seen)


def _retire_stale_meetings(db: Session, term_id: int, seen: set[_MeetingKey]) -> int:
    """Delete a term's meeting blocks that were absent from a complete run."""
    stale = [
        meeting
        for meeting in db.query(Meeting).filter_by(term_id=term_id).all()
        if (
            meeting.term_id,
            meeting.source_record_id,
            meeting.day_of_week,
            meeting.start_time,
        )
        not in seen
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
    """Run the pipeline, persist its output, and record the import result."""
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
