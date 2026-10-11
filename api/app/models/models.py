# SQLAlchemy models for the application
# First import libraries models will use
from datetime import date, datetime, time
from enum import Enum

# Import SQLAlchemy libraries for columns and constraints
from sqlalchemy import (
    DDL,
    CheckConstraint,
    ColumnElement,
    Computed,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
    cast,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.types import UserDefinedType

# Import SQLAlchemy libraries for relationships
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import base class for db models
from app.db import Base


# Postgres has no built-in time-of-day range, so this defines `timerange`,
# following the Postgres docs' example. btree_gist lets one GiST index hold
# the integer columns alongside the range. Alembic's add_time_ranges
# migration runs the same statements; these run on create_all, as in tests.
TIMERANGE_DDL = (
    "CREATE EXTENSION IF NOT EXISTS btree_gist",
    """
    CREATE OR REPLACE FUNCTION time_subtype_diff(x time, y time) RETURNS float8
    AS 'SELECT EXTRACT(EPOCH FROM (x - y))' LANGUAGE sql STRICT IMMUTABLE
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'timerange') THEN
            CREATE TYPE timerange AS RANGE (
                subtype = time, subtype_diff = time_subtype_diff
            );
        END IF;
    END $$
    """,
)
DROP_TIMERANGE_DDL = (
    "DROP TYPE IF EXISTS timerange",
    "DROP FUNCTION IF EXISTS time_subtype_diff(time, time)",
)

for statement in TIMERANGE_DDL:
    event.listen(Base.metadata, "before_create", DDL(statement))
for statement in DROP_TIMERANGE_DDL:
    event.listen(Base.metadata, "after_drop", DDL(statement))


class TimeRange(UserDefinedType):
    """The `timerange` type. Only queried with range operators, never read."""

    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "timerange"


# Half-open, like the times themselves: a class ending at 11:00 and the next
# starting at 11:00 don't overlap.
TIME_RANGE_SQL = "timerange(start_time, end_time, '[)')"


def time_range_column() -> Mapped[str]:
    # Generated from start_time and end_time, so code writes those as before.
    # Deferred keeps it out of ordinary loads.
    return mapped_column(
        TimeRange, Computed(TIME_RANGE_SQL, persisted=True), deferred=True
    )


def contains_time(time_range: ColumnElement, at: time) -> ColumnElement[bool]:
    """Whether `time_range` includes `at`, using its GiST index."""
    return time_range.op("@>")(cast(at, Time))


class TermStatus(str, Enum):
    # Term in session
    ACTIVE = "active"
    # Previous terms, not in session
    ARCHIVED = "archived"


class ImportStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Term(Base):
    __tablename__ = "term"

    # Primary key, unique identifier for the term
    term_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), default="America/Los_Angeles", nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TermStatus] = mapped_column(
        SqlEnum(TermStatus), default=TermStatus.ACTIVE, nullable=False
    )

    meetings: Mapped[list["Meeting"]] = relationship(back_populates="term")
    # Availability intervals associated with this term
    availability_intervals: Mapped[list["AvailabilityInterval"]] = relationship(
        back_populates="term"
    )


class Building(Base):
    __tablename__ = "building"

    building_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String(300))
    included_in_coverage: Mapped[bool] = mapped_column(default=True, nullable=False)

    rooms: Mapped[list["Room"]] = relationship(back_populates="building")


class Room(Base):
    __tablename__ = "room"

    # primary key, unique identifier for the room
    room_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # foreign key to the building table, indicating which building the room belongs to
    building_id: Mapped[int] = mapped_column(
        ForeignKey("building.building_id"), nullable=False
    )
    room_number: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    in_use: Mapped[bool] = mapped_column(default=True, nullable=False)

    building: Mapped["Building"] = relationship(back_populates="rooms")
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="room")
    availability_intervals: Mapped[list["AvailabilityInterval"]] = relationship(
        back_populates="room"
    )

    # Unique constraint to ensure that each room number is unique within a building
    __table_args__ = (UniqueConstraint("building_id", "room_number"),)


class Meeting(Base):
    __tablename__ = "meeting"

    # primary key, unique identifier for the meeting
    meeting_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # foreign key to the room table, indicating which room the meeting is held in
    room_id: Mapped[int] = mapped_column(ForeignKey("room.room_id"), nullable=False)
    # foreign key to the term table, indicating which term the meeting is associated with
    term_id: Mapped[int] = mapped_column(ForeignKey("term.term_id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    meeting_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(200), nullable=False)
    time_range: Mapped[str] = time_range_column()

    room: Mapped["Room"] = relationship(back_populates="meetings")
    term: Mapped["Term"] = relationship(back_populates="meetings")

    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_meeting_day_of_week",
        ),
        # One section can meet in several blocks on the same day, so the
        # identity is the full meeting, scoped to its term.
        UniqueConstraint(
            "term_id",
            "source_record_id",
            "room_id",
            "day_of_week",
            "start_time",
            "end_time",
            name="uq_meeting_identity",
        ),
        # No exclusion constraint: a room's meetings can really overlap,
        # e.g. cross-listed sections, and the import report counts them.
        Index(
            "ix_meeting_time_range",
            "term_id",
            "room_id",
            "day_of_week",
            "time_range",
            postgresql_using="gist",
        ),
    )


class AvailabilityInterval(Base):
    __tablename__ = "availability_interval"

    interval_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.room_id"), nullable=False)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.term_id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(100))
    time_range: Mapped[str] = time_range_column()
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    room: Mapped["Room"] = relationship(back_populates="availability_intervals")
    term: Mapped["Term"] = relationship(back_populates="availability_intervals")

    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_availability_interval_day_of_week",
        ),
        # A room's free intervals on a day never overlap. The constraint's
        # GiST index also serves searches by term, weekday, and time.
        ExcludeConstraint(
            ("term_id", "="),
            ("day_of_week", "="),
            ("time_range", "&&"),
            ("room_id", "="),
            using="gist",
            name="ex_availability_interval_no_overlap",
        ),
    )


class ImportRun(Base):
    __tablename__ = "import_run"

    import_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.term_id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(128))
    parser_version: Mapped[str | None] = mapped_column(String(50))
    computation_version: Mapped[str | None] = mapped_column(String(50))
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_imported: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    # Rejected sections per `ingestion.filter.classify` reason, e.g.
    # {"online": 40}. NULL for runs recorded before this was tracked.
    rejection_counts: Mapped[dict[str, int] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql")
    )
    status: Mapped[ImportStatus] = mapped_column(SqlEnum(ImportStatus), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000))
