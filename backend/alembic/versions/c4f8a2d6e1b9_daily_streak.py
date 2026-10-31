"""daily streak: users.current_streak / max_streak / last_active_date

Revision ID: c4f8a2d6e1b9
Revises: e6b2c8d1f4a7
Create Date: 2026-10-31 20:10:00.000000

The Mini App and the bot both count a pupil as "active" on any meaningful
action (open app/bot, open a lesson, submit a quiz). The day is the
Asia/Tashkent (UTC+5) calendar day. Existing pupils start at 0 — no streak is
invented for past days.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a2d6e1b9'
down_revision: Union[str, Sequence[str], None] = 'e6b2c8d1f4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "current_streak", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "users",
        sa.Column("max_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users", sa.Column("last_active_date", sa.Date(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "last_active_date")
    op.drop_column("users", "max_streak")
    op.drop_column("users", "current_streak")
