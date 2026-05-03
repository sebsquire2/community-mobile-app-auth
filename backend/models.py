from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .core.db import Base


class FailedLoginAttempt(Base):
    __tablename__ = "auth_failed_login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, index=True)
    failed_at = Column(DateTime(timezone=True), nullable=False)


class Community(Base):
    __tablename__ = "communities"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    users = relationship("User", back_populates="community")


class Friendship(Base):
    __tablename__ = "friendships"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    friend_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    user = relationship("User", foreign_keys=[user_id], back_populates="friendships")
    friend = relationship("User", foreign_keys=[friend_id], back_populates="friended_by")


class Follow(Base):
    __tablename__ = "follows"

    follower_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    target_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    target = relationship("User", foreign_keys=[target_id], back_populates="follower_links")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=True, unique=True)
    password_hash = Column(String, nullable=True)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    community_id = Column(String, ForeignKey("communities.id"), nullable=True)
    avatar = Column(String, nullable=False, default="")
    allow_followers = Column(Boolean, nullable=False, default=True)
    default_post_visibility = Column(String, nullable=False, default="public")
    hide_community_from_non_friends = Column(Boolean, nullable=False, default=False)
    oauth_provider = Column(String, nullable=True)
    oauth_sub = Column(String, nullable=True)
    onboarding_complete = Column(Boolean, nullable=False, default=True)

    community = relationship("Community", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user")
    friendships = relationship("Friendship", foreign_keys="Friendship.user_id", back_populates="user")
    friended_by = relationship("Friendship", foreign_keys="Friendship.friend_id", back_populates="friend")
    following = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower")
    follower_links = relationship("Follow", foreign_keys="Follow.target_id", back_populates="target")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    user = relationship("User", back_populates="refresh_tokens")
