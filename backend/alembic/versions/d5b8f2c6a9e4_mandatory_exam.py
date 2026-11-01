"""mandatory exam: question.is_exam, exam_attempts table, certificate mark

Revision ID: d5b8f2c6a9e4
Revises: c9f1d3b7e5a2
Create Date: 2026-11-01 09:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b8f2c6a9e4'
down_revision: Union[str, Sequence[str], None] = 'c9f1d3b7e5a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Which questions belong to the final exam — decided by the admin only.
    op.add_column(
        "questions",
        sa.Column(
            "is_exam", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_questions_is_exam", "questions", ["is_exam"])

    # 2) A certificate now knows how it was earned and with which mark.
    op.add_column(
        "certificates",
        sa.Column("issued_via", sa.String(length=8), nullable=False, server_default="course"),
    )
    op.add_column(
        "certificates",
        sa.Column("mark", sa.String(length=4), nullable=True),
    )

    # 3) The exam sitting itself (paper frozen, result + 30-day lock stored).
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("question_ids", sa.JSON(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("score_percent", sa.Integer(), nullable=False),
        sa.Column("mark", sa.String(length=4), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_attempts_user_id", "exam_attempts", ["user_id"])
    op.create_index("ix_exam_attempts_subject_id", "exam_attempts", ["subject_id"])


def downgrade() -> None:
    op.drop_index("ix_exam_attempts_subject_id", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_user_id", table_name="exam_attempts")
    op.drop_table("exam_attempts")
    op.drop_column("certificates", "mark")
    op.drop_column("certificates", "issued_via")
    op.drop_index("ix_questions_is_exam", table_name="questions")
    op.drop_column("questions", "is_exam")
