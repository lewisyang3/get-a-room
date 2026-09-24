"""allow multiple meeting blocks per source section and weekday

Revision ID: e9d4c2a1b7f0
Revises: d3f1a6b2c4e7
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e9d4c2a1b7f0"
down_revision: Union[str, None] = "d3f1a6b2c4e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "meeting_source_record_id_day_of_week_key",
        "meeting",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_meeting_term_source_day_start",
        "meeting",
        ["term_id", "source_record_id", "day_of_week", "start_time"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_meeting_term_source_day_start",
        "meeting",
        type_="unique",
    )
    op.create_unique_constraint(
        "meeting_source_record_id_day_of_week_key",
        "meeting",
        ["source_record_id", "day_of_week"],
    )
