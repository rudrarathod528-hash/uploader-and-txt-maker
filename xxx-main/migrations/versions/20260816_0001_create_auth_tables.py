"""Create users and refresh token tables.

Revision ID: 20260816_0001
Revises: None
Create Date: 2026-08-16
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260816_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
        sa.Column("phone_e164", sa.String(length=32), nullable=True),
        sa.Column("username_normalized", sa.String(length=64), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email_normalized IS NOT NULL OR phone_e164 IS NOT NULL "
            "OR username_normalized IS NOT NULL",
            name="ck_users_has_identifier",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_email_normalized", "users", ["email_normalized"], unique=True
    )
    op.create_index("uq_users_phone_e164", "users", ["phone_e164"], unique=True)
    op.create_index(
        "uq_users_username_normalized",
        "users",
        ["username_normalized"],
        unique=True,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("uq_users_username_normalized", table_name="users")
    op.drop_index("uq_users_phone_e164", table_name="users")
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.drop_table("users")
