"""course certificates: issued once per pupil + subject

Revision ID: f2c7a9e5d1b8
Revises: d8a4c6e2f9b3
Create Date: 2026-10-31 22:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c7a9e5d1b8'
down_revision: Union[str, Sequence[str], None] = 'd8a4c6e2f9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "certificates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "subject_id", sa.Integer(), sa.ForeignKey("subjects.id"), nullable=False
        ),
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("pupil_name", sa.String(length=128), nullable=False),
        sa.Column("grade_name", sa.String(length=32), nullable=False),
        sa.Column("subject_name", sa.String(length=128), nullable=False),
        sa.Column("score_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "subject_id", name="uq_certificates_user_subject"),
    )
    op.create_index("ix_certificates_user_id", "certificates", ["user_id"])
    op.create_index("ix_certificates_subject_id", "certificates", ["subject_id"])
    op.create_index("ix_certificates_code", "certificates", ["code"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_certificates_code", table_name="certificates")
    op.drop_index("ix_certificates_subject_id", table_name="certificates")
    op.drop_index("ix_certificates_user_id", table_name="certificates")
    op.drop_table("certificates")
