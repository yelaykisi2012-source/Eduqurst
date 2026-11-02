"""chat rooms as rows (+ members, room pictures, message media, teacher flag)

The chat used to be addressed by (kind, grade_id) — enough for "one room per
class + the e'lonxona". The "+" button needs more: a room now has a name, a bio,
a picture and people, so it becomes a real row. This migration also turns
`is_teacher` on (the secret-code staff flag) and lets a message carry one file.

Existing messages are NOT rebuilt: every (kind, grade_id) pair that actually has
rows gets a room, and each row's room_id is filled in. Nothing can be hidden by
a wrong id here — see _ensure_room, which creates a room for any pair the grades
table no longer knows about.

Revision ID: a4c9e7f2b6d1
Revises: f7a3c1e9d2b5
Create Date: 2026-11-01 21:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c9e7f2b6d1'
down_revision: Union[str, Sequence[str], None] = 'f7a3c1e9d2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEWS_NAME = "E'lonxona"
STAFF_NAME = "O‘qituvchilar xonasi"


def _room_id(bind, kind: str, grade_id: int | None) -> int | None:
    """The id of the system room for this pair, or None."""
    if grade_id is None:
        row = bind.execute(
            sa.text("SELECT id FROM chat_rooms WHERE kind = :kind AND grade_id IS NULL"),
            {"kind": kind},
        ).first()
    else:
        row = bind.execute(
            sa.text("SELECT id FROM chat_rooms WHERE kind = :kind AND grade_id = :grade_id"),
            {"kind": kind, "grade_id": grade_id},
        ).first()
    return row.id if row else None


def _ensure_room(bind, kind: str, grade_id: int | None, name: str, emoji: str) -> None:
    """Insert one system room if it is not there yet (idempotent per pair).

    The pair is tested with two plain statements instead of one null-safe
    comparison: `x = :param` with a NULL parameter makes Postgres guess at the
    parameter type, and `false` (not `0`) is what both engines accept for a
    boolean literal.
    """
    if _room_id(bind, kind, grade_id) is not None:
        return
    if grade_id is None:
        bind.execute(
            sa.text(
                "INSERT INTO chat_rooms (kind, grade_id, name, emoji, is_closed) "
                "VALUES (:kind, NULL, :name, :emoji, false)"
            ),
            {"kind": kind, "name": name, "emoji": emoji},
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO chat_rooms (kind, grade_id, name, emoji, is_closed) "
                "VALUES (:kind, :grade_id, :name, :emoji, false)"
            ),
            {"kind": kind, "grade_id": grade_id, "name": name, "emoji": emoji},
        )


def upgrade() -> None:
    # 1) A teacher is a person who knows the code — not an admin.
    op.add_column(
        "users",
        sa.Column("is_teacher", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 2) Rooms. created_at is nullable here (like every other timestamp column in
    #    this schema) — the ORM always fills it, and a hand-written row must not
    #    fail because of it.
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False, server_default="group"),
        sa.Column("grade_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("bio", sa.String(length=200), nullable=True),
        sa.Column("emoji", sa.String(length=8), nullable=False, server_default="💬"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "grade_id"),
    )
    op.create_index("ix_chat_rooms_grade_id", "chat_rooms", ["grade_id"])
    op.create_index("ix_chat_rooms_created_by", "chat_rooms", ["created_by"])

    bind = op.get_bind()

    # 3) The three system rooms, then the class rooms from the grades table.
    _ensure_room(bind, "news", None, NEWS_NAME, "📣")
    _ensure_room(bind, "staff", None, STAFF_NAME, "🧑‍🏫")
    for grade_id, grade_name in bind.execute(
        sa.text("SELECT id, name FROM grades ORDER BY id")
    ).fetchall():
        _ensure_room(bind, "grade", grade_id, grade_name, "💬")

    # 4) Message -> room. A nullable column first, backfilled, because an
    #    existing row cannot be created pointing at a room that does not exist.
    op.add_column(
        "chat_messages",
        sa.Column("room_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_chat_messages_room_id", "chat_messages", ["room_id"])

    # Every pair that has messages must have a room, including a grade that was
    # deleted since — otherwise those messages would belong to nowhere.
    for kind, grade_id in bind.execute(
        sa.text(
            "SELECT DISTINCT kind, grade_id FROM chat_messages WHERE room_id IS NULL"
        )
    ).fetchall():
        _ensure_room(bind, kind, grade_id, kind, "💬")

    # The room lookup is done per pair with bound params: portable across
    # Postgres and SQLite (no "IS NOT DISTINCT FROM", which SQLite lacks).
    for kind, grade_id in bind.execute(
        sa.text("SELECT DISTINCT kind, grade_id FROM chat_messages")
    ).fetchall():
        room = _room_id(bind, kind, grade_id)
        if room is None:
            continue
        if grade_id is None:
            bind.execute(
                sa.text(
                    "UPDATE chat_messages SET room_id = :room "
                    "WHERE room_id IS NULL AND kind = :kind AND grade_id IS NULL"
                ),
                {"room": room, "kind": kind},
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE chat_messages SET room_id = :room "
                    "WHERE room_id IS NULL AND kind = :kind AND grade_id = :grade_id"
                ),
                {"room": room, "kind": kind, "grade_id": grade_id},
            )

    left = bind.execute(
        sa.text("SELECT COUNT(*) FROM chat_messages WHERE room_id IS NULL")
    ).scalar()
    if left:
        # Cannot happen with the loop above; loud beats silently orphaning rows.
        raise RuntimeError(f"{left} chat messages could not be assigned a room")

    # The index the poll uses every few seconds: one room, visible, after an id.
    op.create_index(
        "ix_chat_room_id_visible", "chat_messages", ["room_id", "status", "id"]
    )
    # batch_alter_table, not op.create_foreign_key: SQLite cannot ALTER a
    # constraint at all (it would raise NotImplementedError), while Postgres —
    # the only engine this runs against in production — gets a plain
    # ALTER TABLE ... ADD CONSTRAINT, because batch mode only recreates a table
    # when the dialect truly needs it.
    with op.batch_alter_table("chat_messages") as batch:
        batch.create_foreign_key(
            "fk_chat_messages_room", "chat_rooms", ["room_id"], ["id"],
            ondelete="CASCADE",
        )

    # 5) Who is in a room (only group rooms carry real rows; see the model).
    op.create_table(
        "chat_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=8), nullable=False, server_default="owner"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id"),
    )
    op.create_index("ix_chat_members_room_id", "chat_members", ["room_id"])
    op.create_index("ix_chat_members_user_id", "chat_members", ["user_id"])

    # 6) A room picture — bytes in Postgres, exactly like a profile picture.
    op.create_table(
        "chat_room_avatars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("mime", sa.String(length=16), nullable=False, server_default="image/jpeg"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="256"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_chat_room_avatars_room_id", "chat_room_avatars", ["room_id"])
    op.create_index("ix_chat_room_avatars_slug", "chat_room_avatars", ["slug"])

    # 7) One file per message: picture/GIF as bytes, video as a Telegram file_id.
    op.create_table(
        "chat_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=6), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False, server_default="image/jpeg"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        sa.Column("file_id", sa.String(length=160), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_chat_media_message_id", "chat_media", ["message_id"])
    op.create_index("ix_chat_media_slug", "chat_media", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_chat_media_slug", table_name="chat_media")
    op.drop_index("ix_chat_media_message_id", table_name="chat_media")
    op.drop_table("chat_media")
    op.drop_index("ix_chat_room_avatars_slug", table_name="chat_room_avatars")
    op.drop_index("ix_chat_room_avatars_room_id", table_name="chat_room_avatars")
    op.drop_table("chat_room_avatars")
    op.drop_index("ix_chat_members_user_id", table_name="chat_members")
    op.drop_index("ix_chat_members_room_id", table_name="chat_members")
    op.drop_table("chat_members")
    # The indexes go first (plain DROP INDEX works on both engines), then the
    # column and its FK together — see the batch note in upgrade().
    op.drop_index("ix_chat_room_id_visible", table_name="chat_messages")
    op.drop_index("ix_chat_messages_room_id", table_name="chat_messages")
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("fk_chat_messages_room", type_="foreignkey")
        batch.drop_column("room_id")
    op.drop_index("ix_chat_rooms_created_by", table_name="chat_rooms")
    op.drop_index("ix_chat_rooms_grade_id", table_name="chat_rooms")
    op.drop_table("chat_rooms")
    op.drop_column("users", "is_teacher")
