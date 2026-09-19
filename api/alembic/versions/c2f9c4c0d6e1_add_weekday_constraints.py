"""add weekday constraints

Revision ID: c2f9c4c0d6e1
Revises: a75e13b5b82d
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2f9c4c0d6e1"
down_revision: Union[str, None] = "a75e13b5b82d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_meeting_day_of_week",
        "meeting",
        "day_of_week BETWEEN 0 AND 6",
    )
    op.create_check_constraint(
        "ck_availability_interval_day_of_week",
        "availability_interval",
        "day_of_week BETWEEN 0 AND 6",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_availability_interval_day_of_week",
        "availability_interval",
        type_="check",
    )
    op.drop_constraint(
        "ck_meeting_day_of_week",
        "meeting",
        type_="check",
    )
