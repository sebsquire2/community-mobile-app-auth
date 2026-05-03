"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "communities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("community_id", sa.String(), nullable=True),
        sa.Column("avatar", sa.String(), nullable=False, server_default=""),
        sa.Column("allow_followers", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_post_visibility", sa.String(), nullable=False, server_default="public"),
        sa.Column("hide_community_from_non_friends", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("oauth_provider", sa.String(), nullable=True),
        sa.Column("oauth_sub", sa.String(), nullable=True),
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    op.create_table(
        "auth_failed_login_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_failed_login_attempts_email", "auth_failed_login_attempts", ["email"])

    op.create_table(
        "friendships",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("friend_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["friend_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "friend_id"),
    )

    op.create_table(
        "follows",
        sa.Column("follower_id", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["follower_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("follower_id", "target_id"),
    )
    op.create_index("ix_follows_target_id", "follows", ["target_id"])

    # Seed a default community so registration works out of the box.
    op.execute(
        "INSERT INTO communities (id, name, created_at) VALUES "
        "('community-default', 'Default Community', NOW())"
    )


def downgrade() -> None:
    op.drop_table("follows")
    op.drop_table("friendships")
    op.drop_table("auth_failed_login_attempts")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("communities")
