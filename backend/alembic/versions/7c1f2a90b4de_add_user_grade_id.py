"""add users.grade_id (per-pupil selected grade, 1..11)

Revision ID: 7c1f2a90b4de
Revises: 4354ae42af67
Create Date: 2026-10-30 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1f2a90b4de'
down_revision: Union[str, Sequence[str], None] = '4354ae42af67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("grade_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_grade_id", "users", "grades", ["grade_id"], ["id"]
    )
    op.create_index(
        op.f("ix_users_grade_id"), "users", ["grade_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_grade_id"), table_name="users")
    op.drop_constraint("fk_users_grade_id", "users", type_="foreignkey")
    op.drop_column("users", "grade_id")
