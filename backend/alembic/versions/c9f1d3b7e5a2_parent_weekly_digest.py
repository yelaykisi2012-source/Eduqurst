"""parent weekly digest: parent link columns on users

Revision ID: c9f1d3b7e5a2
Revises: b7e3c1f9a2d4
Create Date: 2026-11-01 00:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f1d3b7e5a2'
down_revision: Union[str, Sequence[str], None] = 'b7e3c1f9a2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("parent_telegram_id", sa.BigInteger(), nullable=True)
    )
    op.create_index(
        "ix_users_parent_telegram_id", "users", ["parent_telegram_id"]
    )
    op.add_column("users", sa.Column("parent_name", sa.String(length=128), nullable=True))
    op.add_column(
        "users", sa.Column("parent_link_code", sa.String(length=16), nullable=True)
    )
    op.create_index(
        "ix_users_parent_link_code", "users", ["parent_link_code"], unique=True
    )
    op.add_column(
        "users",
        sa.Column("parent_link_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "parent_link_expires_at")
    op.drop_index("ix_users_parent_link_code", table_name="users")
    op.drop_column("users", "parent_link_code")
    op.drop_column("users", "parent_name")
    op.drop_index("ix_users_parent_telegram_id", table_name="users")
    op.drop_column("users", "parent_telegram_id")
