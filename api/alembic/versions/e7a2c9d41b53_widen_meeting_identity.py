"""widen meeting identity to the full meeting block

Revision ID: e7a2c9d41b53
Revises: e9d4c2a1b7f0
Create Date: 2026-09-23

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e7a2c9d41b53"
down_revision: Union[str, None] = "e9d4c2a1b7f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adds room_id and end_time to e9d4c2a1b7f0's identity, so two blocks
    # starting together in different rooms don't collide, and so a section
    # is reconciled on exactly the fields persist.py compares.
    op.drop_constraint("uq_meeting_term_source_day_start", "meeting", type_="unique")
    op.create_unique_constraint(
        "uq_meeting_identity",
        "meeting",
        [
            "term_id",
            "source_record_id",
            "room_id",
            "day_of_week",
            "start_time",
            "end_time",
        ],
    )


def downgrade() -> None:
    # Fails if a section has two blocks with the same day and start time
    # (e.g. in different rooms) - the narrower identity can't hold both.
    op.drop_constraint("uq_meeting_identity", "meeting", type_="unique")
    op.create_unique_constraint(
        "uq_meeting_term_source_day_start",
        "meeting",
        ["term_id", "source_record_id", "day_of_week", "start_time"],
    )
