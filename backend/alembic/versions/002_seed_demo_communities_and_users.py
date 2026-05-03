"""seed demo communities and users

Revision ID: 002_seed_demo_communities_and_users
Revises: 001_initial_schema
Create Date: 2025-01-02 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "002_seed_demo_data"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None

# All demo users share this password: password123
_PW = "$argon2id$v=19$m=65536,t=3,p=2$uXnRbvAVzdBLe+VN0l822A$aiWVj1+l76fzW9MUe+7i8NkOVkMiUio9f7mRHEK3yfU"


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO communities (id, name, created_at) VALUES
          ('community-runners', 'Runners Club', NOW()),
          ('community-books',   'Book Club',    NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )

    # Six demo users spread across all three communities.
    #
    # alice  — Runners Club,  community visible to everyone
    # bob    — Runners Club,  community hidden from non-friends
    # carol  — Book Club,     community visible to everyone
    # dave   — Book Club,     community visible to everyone
    # eve    — Default Community
    # frank  — no community yet (NULL)
    op.execute(
        f"""
        INSERT INTO users
          (id, username, email, password_hash, display_name, community_id,
           hide_community_from_non_friends, created_at)
        VALUES
          ('user-demo-alice', 'alice',  'alice@example.com', '{_PW}',
           'Alice',  'community-runners', false, NOW()),
          ('user-demo-bob',   'bob',    'bob@example.com',   '{_PW}',
           'Bob',    'community-runners', true,  NOW()),
          ('user-demo-carol', 'carol',  'carol@example.com', '{_PW}',
           'Carol',  'community-books',   false, NOW()),
          ('user-demo-dave',  'dave',   'dave@example.com',  '{_PW}',
           'Dave',   'community-books',   false, NOW()),
          ('user-demo-eve',   'eve',    'eve@example.com',   '{_PW}',
           'Eve',    'community-default', false, NOW()),
          ('user-demo-frank', 'frank',  'frank@example.com', '{_PW}',
           'Frank',  NULL,                false, NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM users WHERE id IN "
        "('user-demo-alice','user-demo-bob','user-demo-carol',"
        " 'user-demo-dave','user-demo-eve','user-demo-frank')"
    )
    op.execute(
        "DELETE FROM communities WHERE id IN "
        "('community-runners','community-books')"
    )
