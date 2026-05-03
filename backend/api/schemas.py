from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiUser(ApiModel):
    id: str
    username: str
    display_name: str
    community_id: Optional[str] = None
    avatar: str
    allow_followers: bool
    default_post_visibility: Literal["public", "community", "followers", "private"]
    hide_community_from_non_friends: bool
    onboarding_complete: bool
    viewer_relationship: Optional[Literal["self", "friend", "follower", "stranger"]] = None


class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class RevokeSessionsRequest(BaseModel):
    user_id: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    displayName: str


class GoogleOAuthRequest(BaseModel):
    id_token: str


class AppleOAuthRequest(BaseModel):
    id_token: str
    display_name: Optional[str] = None
