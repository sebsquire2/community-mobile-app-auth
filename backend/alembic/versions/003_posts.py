"""add posts table

Revision ID: 003_posts
Revises: 002_seed_demo_data
Create Date: 2025-01-03 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003_posts"
down_revision = "002_seed_demo_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("community_id", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_user_id", "posts", ["user_id"])
    op.create_index("ix_posts_community_id", "posts", ["community_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.execute("""
        INSERT INTO posts (id, user_id, community_id, body, visibility, created_at) VALUES
        ('post-alice-001', 'user-demo-alice', 'community-runners',
         'Just hit a new PB — 5k in 23:15!', 'public', NOW() - INTERVAL '3 hours'),
        ('post-alice-002', 'user-demo-alice', 'community-runners',
         'Reminder: Saturday run starts at 7am sharp. Lace up!', 'community', NOW() - INTERVAL '1 hour'),
        ('post-bob-001',   'user-demo-bob',   'community-runners',
         'New trail route mapped and ready — 8km loop.', 'public', NOW() - INTERVAL '5 hours'),
        ('post-carol-001', 'user-demo-carol', 'community-books',
         'Finished the Dostoevsky. Worth every page.', 'public', NOW() - INTERVAL '2 hours'),
        ('post-carol-002', 'user-demo-carol', 'community-books',
         'Book club meeting moved to Thursday — members only heads-up!', 'community', NOW() - INTERVAL '30 minutes'),
        ('post-dave-001',  'user-demo-dave',  'community-books',
         'Found a first edition at a charity shop 👀', 'public', NOW() - INTERVAL '4 hours'),
        ('post-eve-001',   'user-demo-eve',   'community-default',
         'Hey everyone, good to be here!', 'public', NOW() - INTERVAL '6 hours')
    """)


def downgrade() -> None:
    op.drop_index("ix_posts_created_at", "posts")
    op.drop_index("ix_posts_community_id", "posts")
    op.drop_index("ix_posts_user_id", "posts")
    op.drop_table("posts")
