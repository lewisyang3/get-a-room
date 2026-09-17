from dataclasses import dataclass, field
from datetime import time


@dataclass(frozen=True)
class ParsedMeeting:
    day_of_week: int  # 0=Mon, ..., 6=Sun
    start_time: time
    end_time: time


@dataclass
class ParsedSection:
    source_record_id: str
    slug: str
    section_type: str
    building_name: str | None
    room_number: str | None
    location_raw: str | None
    meetings: list[ParsedMeeting] = field(default_factory=list)
    rejection_reason: str | None = None
