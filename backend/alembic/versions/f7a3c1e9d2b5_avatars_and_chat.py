"""profile pictures (user_avatars) + community chat (chat_messages)

Revision ID: f7a3c1e9d2b5
Revises: d5b8f2c6a9e4
Create Date: 2026-11-01 14:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a3c1e9d2b5'
down_revision: Union[str, Sequence[str], None] = 'd5b8f2c6a9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Profile picture: small re-encoded bytes (Render's disk is ephemeral, so
    #    the picture lives in Postgres) behind an unguessable rotating slug.
    op.create_table(
        "user_avatars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("mime", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=12), nullable=False, server_default="upload"),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_user_avatars_user_id", "user_avatars", ["user_id"])
    op.create_index("ix_user_avatars_slug", "user_avatars", ["slug"])

    # 2) Community chat: one room per grade + the school-wide e'lonxona.
    #    `status` is what lets both moderation modes (immediate vs. approval
    #    queue) coexist — CHAT_PREMODERATION decides which one new messages use.
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False, server_default="grade"),
        sa.Column("grade_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False, server_default="approved"),
        sa.Column("reject_reason", sa.String(length=160), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_grade_id", "chat_messages", ["grade_id"])
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])
    # The one query the app runs constantly: "this room, visible, newest first".
    op.create_index(
        "ix_chat_room_visible",
        "chat_messages",
        ["kind", "grade_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_room_visible", table_name="chat_messages")
    op.drop_index("ix_chat_messages_user_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_grade_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_user_avatars_slug", table_name="user_avatars")
    op.drop_index("ix_user_avatars_user_id", table_name="user_avatars")
    op.drop_table("user_avatars")
