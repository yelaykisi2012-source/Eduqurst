"""web accounts: nullable telegram_id + login/password_hash

Revision ID: e6b2c8d1f4a7
Revises: a3f1c2d9e4b7
Create Date: 2026-10-31 15:40:00.000000

Pupils without Telegram register with a login + password. They share the same
users table, grade system, progress and stars as Telegram pupils, so:
  * users.telegram_id becomes NULLABLE (web accounts have no Telegram id)
  * users.login (lowercase, unique) and users.password_hash (scrypt$...) appear
Existing Telegram rows are untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b2c8d1f4a7'
down_revision: Union[str, Sequence[str], None] = 'a3f1c2d9e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.add_column("users", sa.Column("login", sa.String(length=32), nullable=True))
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    # Postgres allows many NULLs in a unique index, so Telegram pupils (all
    # with login = NULL) never collide; only real logins must be unique.
    op.create_index("ix_users_login", "users", ["login"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    # NOTE: intentionally NOT deleting web accounts here. If any exist,
    # re-making telegram_id NOT NULL fails and Postgres rolls the whole
    # migration back — that is safer than silently destroying accounts.
    op.drop_index("ix_users_login", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "login")
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
