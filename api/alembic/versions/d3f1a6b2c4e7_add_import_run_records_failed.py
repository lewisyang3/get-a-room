"""add import_run records_failed

Revision ID: d3f1a6b2c4e7
Revises: c2f9c4c0d6e1
Create Date: 2026-09-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3f1a6b2c4e7"
down_revision: Union[str, None] = "c2f9c4c0d6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_run",
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("import_run", "records_failed", server_default=None)


def downgrade() -> None:
    op.drop_column("import_run", "records_failed")
