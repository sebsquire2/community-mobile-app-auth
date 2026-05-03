from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

import jwt
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.security.auth import (
    bearer_scheme,
    decode_access_token,
    get_current_user,
    hash_password,
    issue_tokens_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from backend.security.auth_rate_limit import (
    check_email_rate_limit,
    clear_login_attempts,
    record_failed_login,
)
from backend.core.dependencies import get_db, require_admin_key
from backend.models import Community, Follow, Friendship, RefreshToken, User
from backend.core.rate_limit import limiter

from backend.api.schemas import (
    ApiCommunity,
    ApiUser,
    AppleOAuthRequest,
    GoogleOAuthRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    RevokeSessionsRequest,
    UpdateMeRequest,
)

GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_JWKS_URI = "https://appleid.apple.com/auth/keys"

_google_jwks_client: Optional[PyJWKClient] = None
_apple_jwks_client: Optional[PyJWKClient] = None


def _get_google_jwks_client() -> PyJWKClient:
    global _google_jwks_client
    if _google_jwks_client is None:
        _google_jwks_client = PyJWKClient(GOOGLE_JWKS_URI, cache_keys=True)
    return _google_jwks_client


def _get_apple_jwks_client() -> PyJWKClient:
    global _apple_jwks_client
    if _apple_jwks_client is None:
        _apple_jwks_client = PyJWKClient(APPLE_JWKS_URI, cache_keys=True)
    return _apple_jwks_client


def _verify_google_id_token(id_token: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    try:
        signing_key = _get_google_jwks_client().get_signing_key_from_jwt(id_token)
        return jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Google ID token") from exc


def _verify_apple_id_token(id_token: str) -> dict:
    client_id = os.getenv("APPLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Apple OAuth not configured")
    try:
        signing_key = _get_apple_jwks_client().get_signing_key_from_jwt(id_token)
        return jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=client_id)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid Apple ID token") from exc


def _username_from(base: str, db: Session) -> str:
    slug = re.sub(r"[^a-z0-9]", "", base.lower())[:20] or "user"
    candidate = slug
    counter = 1
    while db.execute(select(User).where(User.username == candidate)).scalar_one_or_none():
        candidate = f"{slug}{counter}"
        counter += 1
    return candidate


def _viewer_relationship(
    viewer: Optional[User], target: User, db: Session
) -> Literal["self", "friend", "follower", "stranger"]:
    if not viewer:
        return "stranger"
    if viewer.id == target.id:
        return "self"
    is_friend = db.execute(
        select(func.count()).select_from(Friendship).where(
            Friendship.user_id == viewer.id,
            Friendship.friend_id == target.id,
        )
    ).scalar_one() > 0
    if is_friend:
        return "friend"
    is_following = db.execute(
        select(func.count()).select_from(Follow).where(
            Follow.follower_id == viewer.id,
            Follow.target_id == target.id,
        )
    ).scalar_one() > 0
    return "follower" if is_following else "stranger"


def _serialize_user(user: User, viewer: Optional[User], db: Session) -> dict:
    """
    Serialize a user for an API response, filtering sensitive fields based on the
    viewer's relationship to the target. Data is withheld server-side — it never
    reaches the client — rather than being sent and hidden in the UI.
    """
    relationship = _viewer_relationship(viewer, user, db)
    can_see_community = (
        relationship in ("self", "friend")
        or not user.hide_community_from_non_friends
    )
    return ApiUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        community_id=user.community_id if can_see_community else None,
        avatar=user.avatar,
        allow_followers=user.allow_followers,
        default_post_visibility=user.default_post_visibility,
        hide_community_from_non_friends=user.hide_community_from_non_friends,
        onboarding_complete=user.onboarding_complete,
        viewer_relationship=relationship,
    ).model_dump(by_alias=True)


def _find_or_create_oauth_user(
    db: Session,
    *,
    provider: str,
    sub: str,
    email: Optional[str],
    display_name: Optional[str],
) -> User:
    # 1. Exact match on provider + sub (returning OAuth user)
    user = db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_sub == sub)
    ).scalar_one_or_none()
    if user:
        return user

    # 2. Email match — link OAuth provider to existing password account
    if email:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            user.oauth_provider = provider
            user.oauth_sub = sub
            db.commit()
            return user

    # 3. Create new user, optionally assigning them to the first available community
    default_community = db.execute(select(Community).limit(1)).scalar_one_or_none()
    name = (display_name or "").strip() or (email.split("@")[0] if email else provider)
    username = _username_from(name, db)
    user = User(
        id=f"user-{uuid4().hex[:10]}",
        username=username,
        email=email,
        password_hash=None,
        display_name=name,
        community_id=default_community.id if default_community else None,
        oauth_provider=provider,
        oauth_sub=sub,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


router = APIRouter()


@router.post("/auth/login")
@limiter.limit("10/minute")
def login(
    request: Request, payload: LoginRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    email = (payload.email or "").strip().lower()
    password = payload.password or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    check_email_rate_limit(db, email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user and not user.password_hash and user.oauth_provider:
        raise HTTPException(
            status_code=400,
            detail=f"This account uses {user.oauth_provider.capitalize()} sign-in. Please use that instead.",
        )
    if not user or not verify_password(password, user.password_hash or ""):
        record_failed_login(db, email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_login_attempts(db, email)
    tokens = issue_tokens_for_user(db, user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "user": _serialize_user(user, user, db),
    }


@router.post("/auth/refresh")
@limiter.limit("30/minute")
def refresh_tokens(
    request: Request, payload: RefreshRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    tokens, _user_id = rotate_refresh_token(db, payload.refresh_token)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
    }


@router.post("/auth/logout")
def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    revoke_refresh_token(db, current_user.id, payload.refresh_token)
    return {"success": True}


@router.post("/auth/revoke-sessions")
def revoke_all_sessions(
    payload: RevokeSessionsRequest,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    tokens = db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == payload.user_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).scalars().all()
    for token in tokens:
        token.revoked_at = now
    db.commit()
    user = db.get(User, payload.user_id)
    if user and user.email:
        clear_login_attempts(db, user.email)
    return {"user_id": payload.user_id, "revoked": len(tokens)}


@router.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
def register(
    request: Request, payload: RegisterRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    email = payload.email.strip().lower()
    if not email or not payload.password:
        raise HTTPException(status_code=400, detail="Email and password required")
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise HTTPException(status_code=400, detail="Invalid email address") from exc
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not payload.displayName.strip():
        raise HTTPException(status_code=400, detail="Display name required")
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    if payload.communityId is not None:
        community = db.get(Community, payload.communityId)
        if not community:
            raise HTTPException(status_code=404, detail="Community not found")
    else:
        community = db.execute(select(Community).limit(1)).scalar_one_or_none()
    base_username = email.split("@")[0][:20].lower()
    username = base_username
    counter = 1
    while db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        username = f"{base_username}{counter}"
        counter += 1
    user = User(
        id=f"user-{uuid4().hex[:10]}",
        username=username,
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.displayName.strip(),
        community_id=community.id if community else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    tokens = issue_tokens_for_user(db, user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "user": _serialize_user(user, user, db),
    }


@router.post("/auth/google", status_code=200)
@limiter.limit("10/minute")
def oauth_google(
    request: Request, payload: GoogleOAuthRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    claims = _verify_google_id_token(payload.id_token)
    sub = claims.get("sub") or ""
    email = (claims.get("email") or "").strip().lower() or None
    display_name = claims.get("name") or None
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid Google ID token")
    user = _find_or_create_oauth_user(db, provider="google", sub=sub, email=email, display_name=display_name)
    tokens = issue_tokens_for_user(db, user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "user": _serialize_user(user, user, db),
    }


@router.post("/auth/apple", status_code=200)
@limiter.limit("10/minute")
def oauth_apple(
    request: Request, payload: AppleOAuthRequest, db: Session = Depends(get_db)
) -> Dict[str, Any]:
    claims = _verify_apple_id_token(payload.id_token)
    sub = claims.get("sub") or ""
    email = (claims.get("email") or "").strip().lower() or None
    display_name = (payload.display_name or "").strip() or None
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid Apple ID token")
    user = _find_or_create_oauth_user(db, provider="apple", sub=sub, email=email, display_name=display_name)
    tokens = issue_tokens_for_user(db, user)
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "user": _serialize_user(user, user, db),
    }


@router.get("/users/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return _serialize_user(current_user, current_user, db)


def _get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        user_id = decode_access_token(credentials.credentials)
    except Exception:
        return None
    return db.get(User, user_id)


@router.patch("/users/me")
def update_me(
    payload: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if payload.community_id is not None:
        if not db.get(Community, payload.community_id):
            raise HTTPException(status_code=404, detail="Community not found")
        current_user.community_id = payload.community_id
    if payload.display_name is not None:
        if not payload.display_name.strip():
            raise HTTPException(status_code=400, detail="Display name cannot be empty")
        current_user.display_name = payload.display_name.strip()
    if payload.hide_community_from_non_friends is not None:
        current_user.hide_community_from_non_friends = payload.hide_community_from_non_friends
    db.commit()
    db.refresh(current_user)
    return _serialize_user(current_user, current_user, db)


@router.get("/communities")
def list_communities(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(Community, func.count(User.id).label("member_count"))
        .outerjoin(User, User.community_id == Community.id)
        .group_by(Community.id)
        .order_by(Community.name)
    ).all()
    return [
        ApiCommunity(id=r.Community.id, name=r.Community.name, member_count=r.member_count).model_dump(by_alias=True)
        for r in rows
    ]


@router.get("/communities/{community_id}/members")
def list_community_members(
    community_id: str,
    viewer: Optional[User] = Depends(_get_optional_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    if not db.get(Community, community_id):
        raise HTTPException(status_code=404, detail="Community not found")
    members = db.execute(
        select(User).where(User.community_id == community_id).order_by(User.display_name)
    ).scalars().all()
    return [_serialize_user(m, viewer, db) for m in members]


@router.get("/users/{user_id}")
def get_user(
    user_id: str,
    viewer: Optional[User] = Depends(_get_optional_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user, viewer, db)
