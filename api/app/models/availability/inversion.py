from datetime import time


def invert_intervals(
    booked_intervals: list[tuple[time, time]],
    day_start: time = time(7, 0),
    day_end: time = time(22, 0),
) -> list[tuple[time, time]]:
    """
    Converts booked intervals into free intervals.

    Example:
        Booked: [(10:00, 11:00), (13:00, 15:00)]
        Free:   [(07:00, 10:00), (11:00, 13:00), (15:00, 22:00)]
    """

    # Rejects an invalid daily time window.
    if day_start >= day_end:
        raise ValueError("day_start must be earlier than day_end")

    # Removes meetings that fall completely outside the daily window.
    relevant_intervals = [
        (start, end)
        for start, end in booked_intervals
        if end > day_start and start < day_end
    ]

    # Clips meetings that extend before or after the daily window.
    clipped_intervals = [
        (max(start, day_start), min(end, day_end)) for start, end in relevant_intervals
    ]

    # Sorts meetings from earliest start time to latest.
    clipped_intervals.sort(key=lambda interval: interval[0])

    # Merges overlapping and back-to-back meetings.
    merged_intervals: list[tuple[time, time]] = []

    for start, end in clipped_intervals:
        # Rejects meetings where the end is not after the start.
        if start >= end:
            raise ValueError("Meeting end must be after meeting start")

        # Adds the first interval.
        if not merged_intervals:
            merged_intervals.append((start, end))
            continue

        # Gets the end of the previous merged interval.
        previous_start, previous_end = merged_intervals[-1]

        # Merges intervals that overlap or touch.
        if start <= previous_end:
            merged_intervals[-1] = (
                previous_start,
                max(previous_end, end),
            )
        else:
            # Keeps separate intervals separate.
            merged_intervals.append((start, end))

    # Stores the resulting free intervals.
    free_intervals: list[tuple[time, time]] = []

    # Tracks the end of the previous booked interval.
    current_time = day_start

    # Finds the gaps between booked intervals.
    for start, end in merged_intervals:
        if current_time < start:
            free_intervals.append((current_time, start))

        current_time = max(current_time, end)

    # Adds any free time remaining at the end of the day.
    if current_time < day_end:
        free_intervals.append((current_time, day_end))

    # Returns all free intervals.
    return free_intervals
