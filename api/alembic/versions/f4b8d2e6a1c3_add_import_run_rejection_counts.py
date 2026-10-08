"""add import_run rejection_counts

Revision ID: f4b8d2e6a1c3
Revises: e7a2c9d41b53
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4b8d2e6a1c3"
down_revision: Union[str, None] = "e7a2c9d41b53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: earlier runs didn't record why sections were rejected.
    op.add_column(
        "import_run",
        sa.Column(
            "rejection_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("import_run", "rejection_counts")
