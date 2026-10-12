from ingestion.types import ParsedSection

# Per GAR-017: these are the section types reliably tied to a scheduled
# room. SEM and STD were added once Fall 2026 pages showed most seminars
# and studios list a real classroom. IND/TUT are never assigned a room;
# anything else observed (FLD, INT, ...) is dropped rather than guessed at.
ROOM_OCCUPYING_TYPES = {"LEC", "DIS", "LAB", "GRP", "REC", "SEM", "STD"}


def _location_rejection_reason(section: ParsedSection) -> str:
    raw = section.location_raw
    if raw is None:
        return "missing_location"
    lowered = raw.lower()
    if "general assignment" in lowered:
        return "general_assignment_requested"
    if "online" in lowered or "internet" in lowered:
        return "online"
    return "unparseable_location"


def classify(section: ParsedSection) -> ParsedSection:
    """Sets rejection_reason on the section (also returned for convenience).

    A section is accepted only if its type reliably occupies a room, it has
    at least one parsed meeting, and it resolved to an actual building/room -
    an in-scope type can still lack a room (e.g. "Requested General
    Assignment"), so this is checked independently of the type filter.
    """
    if section.section_type not in ROOM_OCCUPYING_TYPES:
        section.rejection_reason = (
            f"section_type_not_room_occupying:{section.section_type}"
        )
    elif not section.meetings:
        section.rejection_reason = "no_meetings"
    elif section.building_name is None or section.room_number is None:
        section.rejection_reason = _location_rejection_reason(section)
    else:
        section.rejection_reason = None
    return section


def is_accepted(section: ParsedSection) -> bool:
    return section.rejection_reason is None
