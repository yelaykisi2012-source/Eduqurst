"""add lesson_materials file fields (uploaded video/pdf via Telegram)

Revision ID: a3f1c2d9e4b7
Revises: 7c1f2a90b4de
Create Date: 2026-10-31 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c2d9e4b7'
down_revision: Union[str, Sequence[str], None] = '7c1f2a90b4de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "lesson_materials",
        sa.Column("file_id", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "lesson_materials",
        sa.Column("file_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "lesson_materials",
        sa.Column("file_size", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("lesson_materials", "file_size")
    op.drop_column("lesson_materials", "file_name")
    op.drop_column("lesson_materials", "file_id")
