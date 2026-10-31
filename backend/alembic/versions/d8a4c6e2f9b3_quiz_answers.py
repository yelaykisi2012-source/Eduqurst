"""quiz answers: per-attempt details for "review mistakes"

Revision ID: d8a4c6e2f9b3
Revises: c4f8a2d6e1b9
Create Date: 2026-10-31 21:30:00.000000

Without these rows a wrong answer only existed in the request; the result
screen could not show "what you picked vs. the correct answer". Old attempts
keep working: they simply have no stored answers, so review is empty for them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8a4c6e2f9b3'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2d6e1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "quiz_answers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            sa.ForeignKey("quiz_attempts.id"),
            nullable=False,
        ),
        sa.Column(
            "question_id", sa.Integer(), sa.ForeignKey("questions.id"), nullable=False
        ),
        sa.Column(
            "option_id", sa.Integer(), sa.ForeignKey("answer_options.id"), nullable=True
        ),
        sa.Column("text_answer", sa.String(length=255), nullable=True),
        sa.Column(
            "is_correct", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_quiz_answers_attempt_id", "quiz_answers", ["attempt_id"])
    op.create_index("ix_quiz_answers_question_id", "quiz_answers", ["question_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_quiz_answers_question_id", table_name="quiz_answers")
    op.drop_index("ix_quiz_answers_attempt_id", table_name="quiz_answers")
    op.drop_table("quiz_answers")
