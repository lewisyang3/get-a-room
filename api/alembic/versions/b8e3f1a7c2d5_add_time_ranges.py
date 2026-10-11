"""add GiST-indexed time ranges

Revision ID: b8e3f1a7c2d5
Revises: f4b8d2e6a1c3
Create Date: 2026-10-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b8e3f1a7c2d5"
down_revision: Union[str, None] = "f4b8d2e6a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Half-open, matching how start_time and end_time are already read.
TIME_RANGE_SQL = "timerange(start_time, end_time, '[)')"


class _TimeRange(sa.types.UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "timerange"


def upgrade() -> None:
    # Postgres has no built-in time-of-day range type. btree_gist lets one
    # GiST index hold the integer columns alongside the range.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        CREATE FUNCTION time_subtype_diff(x time, y time) RETURNS float8
        AS 'SELECT EXTRACT(EPOCH FROM (x - y))' LANGUAGE sql STRICT IMMUTABLE
        """
    )
    op.execute(
        "CREATE TYPE timerange AS RANGE "
        "(subtype = time, subtype_diff = time_subtype_diff)"
    )

    # Generated from start_time and end_time; adding it rewrites each table.
    for table in ("meeting", "availability_interval"):
        op.add_column(
            table,
            sa.Column(
                "time_range", _TimeRange(), sa.Computed(TIME_RANGE_SQL, persisted=True)
            ),
        )

    op.create_index(
        "ix_meeting_time_range",
        "meeting",
        ["term_id", "room_id", "day_of_week", "time_range"],
        postgresql_using="gist",
    )
    # Fails if a room already has overlapping free intervals on a day.
    op.execute(
        """
        ALTER TABLE availability_interval
        ADD CONSTRAINT ex_availability_interval_no_overlap
        EXCLUDE USING gist (
            term_id WITH =, day_of_week WITH =, time_range WITH &&, room_id WITH =
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("ex_availability_interval_no_overlap", "availability_interval")
    op.drop_index("ix_meeting_time_range", table_name="meeting")
    for table in ("meeting", "availability_interval"):
        op.drop_column(table, "time_range")
    # Leaves btree_gist installed, in case anything else uses it.
    op.execute("DROP TYPE timerange")
    op.execute("DROP FUNCTION time_subtype_diff(time, time)")
