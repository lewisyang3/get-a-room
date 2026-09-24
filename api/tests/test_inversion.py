from datetime import time

from app.models.availability.inversion import invert_intervals


def test_no_booked_intervals():
    result = invert_intervals([])

    assert result == [
        (time(7, 0), time(22, 0)),
    ]


def test_one_booked_interval():
    result = invert_intervals(
        [
            (time(10, 0), time(11, 0)),
        ]
    )

    assert result == [
        (time(7, 0), time(10, 0)),
        (time(11, 0), time(22, 0)),
    ]


def test_overlapping_intervals_are_merged():
    result = invert_intervals(
        [
            (time(10, 0), time(12, 0)),
            (time(11, 0), time(13, 0)),
        ]
    )

    assert result == [
        (time(7, 0), time(10, 0)),
        (time(13, 0), time(22, 0)),
    ]


def test_back_to_back_intervals_are_merged():
    result = invert_intervals(
        [
            (time(10, 0), time(11, 0)),
            (time(11, 0), time(12, 0)),
        ]
    )

    assert result == [
        (time(7, 0), time(10, 0)),
        (time(12, 0), time(22, 0)),
    ]


def test_multiple_free_gaps():
    result = invert_intervals(
        [
            (time(10, 0), time(11, 0)),
            (time(13, 0), time(15, 0)),
        ]
    )

    assert result == [
        (time(7, 0), time(10, 0)),
        (time(11, 0), time(13, 0)),
        (time(15, 0), time(22, 0)),
    ]


def test_interval_is_clipped_to_day():
    result = invert_intervals(
        [
            (time(6, 0), time(8, 0)),
            (time(21, 0), time(23, 0)),
        ]
    )

    assert result == [
        (time(8, 0), time(21, 0)),
    ]


def test_invalid_interval_raises_error():
    try:
        invert_intervals(
            [
                (time(12, 0), time(11, 0)),
            ]
        )
        assert False
    except ValueError:
        assert True
