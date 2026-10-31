"""matching questions: question_prompts + answer_options.pair_key

Revision ID: b7e3c1f9a2d4
Revises: f2c7a9e5d1b8
Create Date: 2026-10-31 23:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3c1f9a2d4'
down_revision: Union[str, Sequence[str], None] = 'f2c7a9e5d1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "question_prompts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "question_id", sa.Integer(), sa.ForeignKey("questions.id"), nullable=False
        ),
        sa.Column("text", sa.String(length=255), nullable=False),
        sa.Column("pair_key", sa.String(length=32), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_question_prompts_question_id", "question_prompts", ["question_id"]
    )
    op.add_column(
        "answer_options", sa.Column("pair_key", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("answer_options", "pair_key")
    op.drop_index("ix_question_prompts_question_id", table_name="question_prompts")
    op.drop_table("question_prompts")
