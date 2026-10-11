"""The data-quality report for a term's imported schedule (GAR-051).

`build_report` gathers everything from the database, and the CLI's
`import report` prints it. Nothing here writes.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import time, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.queries import searchable_rooms
from app.models.models import (
    AvailabilityInterval,
    Building,
    ImportRun,
    ImportStatus,
    Meeting,
    Room,
    Term,
)

# The hours availability covers: recompute_availability's day_start/day_end.
DAY_START, DAY_END = time(7, 0), time(22, 0)

# Weekdays (0=Mon) and times the sample availability is counted at.
SAMPLE_DAYS = range(5)
SAMPLE_TIMES = (time(10, 0), time(14, 0), time(18, 0))
EXAMPLES = 5

# Words that don't tell two buildings apart: "Dwinelle" and "Dwinelle Hall"
# are probably one building scraped under two names.
_GENERIC_BUILDING_WORDS = {"hall", "building", "bldg", "center", "ctr", "the"}


@dataclass
class LastImport:
    run: ImportRun
    # FAILED runs started after it; the data shown is still this run's.
    failed_since: int


@dataclass
class Coverage:
    buildings: int
    covered_buildings: int
    # Covered buildings the map can't place.
    without_coordinates: list[str]
    rooms: int
    searchable_rooms: int
    sections: int
    meetings: int
    meetings_by_type: dict[str, int]
    # Meetings starting before DAY_START or ending after DAY_END; availability
    # ignores the part outside the window.
    outside_window: int


@dataclass
class Overlap:
    building: str
    room: str
    day_of_week: int
    first: tuple[str, time, time]  # (source_record_id, start, end)
    second: tuple[str, time, time]


@dataclass
class Duplicates:
    # Room numbers in one building that differ only in case, spacing,
    # punctuation or leading zeros, e.g. ["Dwinelle: 0242, 242"].
    similar_rooms: list[str]
    # Building names that differ only by a word like "Hall".
    similar_buildings: list[str]
    # Pairs of different sections meeting in one room at overlapping times.
    # Usually cross-listed courses, but a wrong room parse looks the same.
    overlap_count: int
    overlap_examples: list[Overlap]


@dataclass
class BuildingRooms:
    name: str
    rooms: int
    covered: bool


@dataclass
class FreeRoom:
    building: str
    room: str
    free_until: time


@dataclass
class SampleAvailability:
    # (day_of_week, time) -> searchable rooms free then.
    free_counts: dict[tuple[int, time], int]
    example_at: tuple[int, time]
    examples: list[FreeRoom]


@dataclass
class Report:
    term: Term
    last_import: LastImport | None
    coverage: Coverage
    duplicates: Duplicates
    rooms_by_building: list[BuildingRooms]
    sample: SampleAvailability


def _last_import(db: Session, term_id: int) -> LastImport | None:
    run = db.scalars(
        select(ImportRun)
        .where(
            ImportRun.term_id == term_id,
            ImportRun.status == ImportStatus.COMPLETED,
        )
        .order_by(ImportRun.started_at.desc(), ImportRun.import_id.desc())
        .limit(1)
    ).one_or_none()
    if run is None:
        return None
    failed_since = db.scalar(
        select(func.count()).where(
            ImportRun.term_id == term_id,
            ImportRun.status == ImportStatus.FAILED,
            ImportRun.started_at > run.started_at,
        )
    )
    return LastImport(run=run, failed_since=failed_since)


def _coverage(db: Session, term_id: int) -> Coverage:
    buildings = db.scalar(select(func.count()).select_from(Building))
    covered = db.scalar(
        select(func.count()).where(Building.included_in_coverage.is_(True))
    )
    without_coordinates = list(
        db.scalars(
            select(Building.name)
            .where(
                Building.included_in_coverage.is_(True),
                or_(Building.latitude.is_(None), Building.longitude.is_(None)),
            )
            .order_by(Building.name)
        )
    )
    rooms = db.scalar(select(func.count()).select_from(Room))
    searchable = db.scalar(
        select(func.count())
        .select_from(Room)
        .join(Building, Room.building_id == Building.building_id)
        .where(searchable_rooms())
    )
    in_term = Meeting.term_id == term_id
    sections = db.scalar(
        select(func.count(func.distinct(Meeting.source_record_id))).where(in_term)
    )
    meetings = db.scalar(select(func.count()).where(in_term))
    by_type = dict(
        db.execute(
            select(Meeting.meeting_type, func.count())
            .where(in_term)
            .group_by(Meeting.meeting_type)
            .order_by(func.count().desc(), Meeting.meeting_type)
        ).all()
    )
    outside = db.scalar(
        select(func.count()).where(
            in_term,
            or_(Meeting.start_time < DAY_START, Meeting.end_time > DAY_END),
        )
    )
    return Coverage(
        buildings=buildings,
        covered_buildings=covered,
        without_coordinates=without_coordinates,
        rooms=rooms,
        searchable_rooms=searchable,
        sections=sections,
        meetings=meetings,
        meetings_by_type=by_type,
        outside_window=outside,
    )


def _room_key(room_number: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", room_number.lower())
    return key.lstrip("0") or key


def _building_key(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return " ".join(word for word in words if word not in _GENERIC_BUILDING_WORDS)


def _groups(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Values sharing a key, for keys with more than one distinct value."""
    grouped: dict[str, set[str]] = defaultdict(set)
    for key, value in pairs:
        grouped[key].add(value)
    return [sorted(values) for values in grouped.values() if len(values) > 1]


def _duplicates(db: Session, term_id: int) -> Duplicates:
    rooms = db.execute(
        select(Building.name, Room.room_number)
        .join(Room, Room.building_id == Building.building_id)
        .order_by(Building.name)
    ).all()
    by_building: dict[str, list[str]] = defaultdict(list)
    for building, room_number in rooms:
        by_building[building].append(room_number)
    similar_rooms = [
        f"{building}: {', '.join(group)}"
        for building, numbers in by_building.items()
        for group in _groups([(_room_key(n), n) for n in numbers])
    ]

    names = db.scalars(select(Building.name)).all()
    similar_buildings = sorted(
        ", ".join(group) for group in _groups([(_building_key(n), n) for n in names])
    )

    first, second = aliased(Meeting), aliased(Meeting)
    overlapping = and_(
        second.term_id == first.term_id,
        second.room_id == first.room_id,
        second.day_of_week == first.day_of_week,
        # Each pair once, and never a section against its own other blocks.
        second.source_record_id > first.source_record_id,
        # Half-open: one class ending at 11:00 and the next starting at 11:00
        # don't overlap.
        first.start_time < second.end_time,
        second.start_time < first.end_time,
    )
    pairs = (
        select(first, second, Room.room_number, Building.name)
        .join(second, overlapping)
        .join(Room, Room.room_id == first.room_id)
        .join(Building, Building.building_id == Room.building_id)
        .where(first.term_id == term_id)
    )
    overlap_count = db.scalar(select(func.count()).select_from(pairs.subquery()))
    overlap_examples = [
        Overlap(
            building=building,
            room=room_number,
            day_of_week=a.day_of_week,
            first=(a.source_record_id, a.start_time, a.end_time),
            second=(b.source_record_id, b.start_time, b.end_time),
        )
        for a, b, room_number, building in db.execute(
            pairs.order_by(
                Building.name, Room.room_number, first.day_of_week, first.start_time
            ).limit(EXAMPLES)
        )
    ]
    return Duplicates(
        similar_rooms=similar_rooms,
        similar_buildings=similar_buildings,
        overlap_count=overlap_count,
        overlap_examples=overlap_examples,
    )


def _rooms_by_building(db: Session) -> list[BuildingRooms]:
    rows = db.execute(
        select(
            Building.name,
            func.count(Room.room_id).filter(Room.in_use.is_(True)),
            Building.included_in_coverage,
        )
        .outerjoin(Room, Room.building_id == Building.building_id)
        .group_by(Building.building_id)
        .order_by(Building.name, Building.building_id)
    ).all()
    return [BuildingRooms(name, rooms, covered) for name, rooms, covered in rows]


def _free_at(term_id: int, day_of_week: int, at: time):
    """The searchable rooms' intervals that are free at `at` (half-open)."""
    return (
        select(AvailabilityInterval)
        .join(Room, AvailabilityInterval.room_id == Room.room_id)
        .join(Building, Room.building_id == Building.building_id)
        .where(
            searchable_rooms(),
            AvailabilityInterval.term_id == term_id,
            AvailabilityInterval.day_of_week == day_of_week,
            AvailabilityInterval.start_time <= at,
            AvailabilityInterval.end_time > at,
        )
    )


def _sample(db: Session, term_id: int) -> SampleAvailability:
    free_counts = {
        (day, at): db.scalar(
            select(func.count()).select_from(_free_at(term_id, day, at).subquery())
        )
        for day in SAMPLE_DAYS
        for at in SAMPLE_TIMES
    }
    example_day, example_time = SAMPLE_DAYS[0], SAMPLE_TIMES[0]
    examples = [
        FreeRoom(building=building, room=room_number, free_until=free_until)
        for building, room_number, free_until in db.execute(
            _free_at(term_id, example_day, example_time)
            .with_only_columns(
                Building.name, Room.room_number, AvailabilityInterval.end_time
            )
            .order_by(Building.name, Room.room_number)
            .limit(EXAMPLES)
        )
    ]
    return SampleAvailability(
        free_counts=free_counts,
        example_at=(example_day, example_time),
        examples=examples,
    )


def build_report(db: Session, term: Term) -> Report:
    return Report(
        term=term,
        last_import=_last_import(db, term.term_id),
        coverage=_coverage(db, term.term_id),
        duplicates=_duplicates(db, term.term_id),
        rooms_by_building=_rooms_by_building(db),
        sample=_sample(db, term.term_id),
    )


_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")


def _table(rows: list[tuple[str, ...]], indent: str = "  ") -> list[str]:
    """Left-aligns every column but the last, like `term list`."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]) - 1)]
    return [
        indent
        + "  ".join(
            [cell.ljust(width) for cell, width in zip(row, widths)] + [row[-1]]
        ).rstrip()
        for row in rows
    ]


def _format_last_import(last: LastImport | None) -> list[str]:
    lines = ["Last import"]
    if last is None:
        return lines + ["  None completed."]
    run = last.run
    minutes = round((run.completed_at - run.started_at).total_seconds() / 60)
    # The driver returns the session's zone, which isn't always UTC.
    completed = run.completed_at.astimezone(timezone.utc)
    lines += [
        f"  Import {run.import_id}, completed "
        f"{completed:%Y-%m-%d %H:%M} UTC in {minutes} min",
        f"  {run.records_read} read: {run.records_imported} imported, "
        f"{run.records_rejected} rejected, {run.records_failed} failed",
    ]
    if run.rejection_counts is None:
        lines.append("  Rejection reasons weren't recorded for this run.")
    elif run.rejection_counts:
        lines.append("  Rejected, by reason:")
        reasons = sorted(run.rejection_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        lines += _table([(reason, str(n)) for reason, n in reasons], indent="    ")
    if run.records_failed:
        lines.append(
            "  Some sections failed, so meetings of removed sections weren't "
            "cleaned up."
        )
    if last.failed_since:
        lines.append(
            f"  {last.failed_since} failed run(s) since; the data is still "
            "this import's."
        )
    return lines


def _format_coverage(coverage: Coverage) -> list[str]:
    types = ", ".join(f"{t} {n}" for t, n in coverage.meetings_by_type.items())
    lines = [
        "Coverage",
        f"  Buildings: {coverage.buildings}, {coverage.covered_buildings} in coverage",
    ]
    if coverage.without_coordinates:
        lines.append(
            f"  Covered without coordinates ({len(coverage.without_coordinates)}): "
            + ", ".join(coverage.without_coordinates)
        )
    lines += [
        f"  Rooms: {coverage.rooms}, {coverage.searchable_rooms} searchable",
        f"  Sections with meetings: {coverage.sections}",
        f"  Meetings: {coverage.meetings}" + (f" ({types})" if types else ""),
        f"  Meetings outside {_hhmm(DAY_START)}-{_hhmm(DAY_END)}: "
        f"{coverage.outside_window}"
        + (
            " (availability ignores the part outside)"
            if coverage.outside_window
            else ""
        ),
    ]
    return lines


def _format_duplicates(duplicates: Duplicates) -> list[str]:
    def listed(label: str, items: list[str]) -> list[str]:
        if not items:
            return [f"  {label}: none"]
        return [f"  {label} ({len(items)}):"] + [f"    {item}" for item in items]

    lines = [
        "Duplicate checks",
        "  Exact duplicates: prevented by database constraints",
        *listed("Room numbers that look the same", duplicates.similar_rooms),
        *listed("Building names that look the same", duplicates.similar_buildings),
        f"  Different sections in one room at overlapping times: "
        f"{duplicates.overlap_count} pair(s)",
    ]
    if duplicates.overlap_count:
        lines.append("    Usually cross-listed courses. For example:")
    for o in duplicates.overlap_examples:
        (a_id, a_start, a_end), (b_id, b_start, b_end) = o.first, o.second
        lines.append(
            f"    {o.building} {o.room}, {_DAY_NAMES[o.day_of_week]}: "
            f"{a_id} {_hhmm(a_start)}-{_hhmm(a_end)} and "
            f"{b_id} {_hhmm(b_start)}-{_hhmm(b_end)}"
        )
    return lines


def _format_rooms_by_building(rows: list[BuildingRooms]) -> list[str]:
    if not rows:
        return ["Rooms in use, by building", "  No buildings."]
    return ["Rooms in use, by building"] + _table(
        [
            (row.name, str(row.rooms), "" if row.covered else "(not in coverage)")
            for row in rows
        ]
    )


def _format_sample(sample: SampleAvailability) -> list[str]:
    header = ("",) + tuple(_hhmm(at) for at in SAMPLE_TIMES)
    rows = [header] + [
        (_DAY_NAMES[day],)
        + tuple(str(sample.free_counts[(day, at)]) for at in SAMPLE_TIMES)
        for day in SAMPLE_DAYS
    ]
    day, at = sample.example_at
    lines = ["Sample availability: searchable rooms free"] + _table(rows)
    lines.append(f"  Free {_DAY_NAMES[day]} at {_hhmm(at)}, for example:")
    lines += [
        f"    {room.building} {room.room}, until {_hhmm(room.free_until)}"
        for room in sample.examples
    ] or ["    none"]
    return lines


def format_report(report: Report) -> str:
    term = report.term
    sections = [
        [f"Data-quality report: {term.name} (term {term.term_id})"],
        _format_last_import(report.last_import),
        _format_coverage(report.coverage),
        _format_duplicates(report.duplicates),
        _format_rooms_by_building(report.rooms_by_building),
        _format_sample(report.sample),
    ]
    return "\n\n".join("\n".join(lines) for lines in sections)
