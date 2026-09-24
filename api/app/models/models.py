# SQLAlchemy models for the application
# First import libraries models will use
from datetime import date, datetime, time
from enum import Enum

# Import SQLAlchemy libraries for columns and constraints
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)

# Import SQLAlchemy libraries for relationships
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import base class for db models
from app.db import Base


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
    status: Mapped[ImportStatus] = mapped_column(SqlEnum(ImportStatus), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000))
