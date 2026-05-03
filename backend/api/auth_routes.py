from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request
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
from backend.models import Community, Follow, Friendship, Post, RefreshToken, User
from backend.core.rate_limit import limiter

from backend.api.schemas import (
    ApiCommunity,
    ApiUser,
    LoginRequest,
    LogoutRequest,
    PostCreate,
    RefreshRequest,
    RegisterRequest,
    RevokeSessionsRequest,
    UpdateMeRequest,
)


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
    current_user.token_version += 1
    db.commit()
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
    user = db.get(User, payload.user_id)
    if user:
        user.token_version += 1
        db.commit()
        if user.email:
            clear_login_attempts(db, user.email)
    else:
        db.commit()
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
        claims = decode_access_token(credentials.credentials)
    except Exception:
        return None
    user = db.get(User, claims.user_id)
    if not user or user.token_version != claims.token_version:
        return None
    return user


@router.patch("/users/me")
def update_me(
    payload: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.community_id is not None:
        if not db.get(Community, payload.community_id):
            raise HTTPException(status_code=404, detail="Community not found")
        user.community_id = payload.community_id
    if payload.display_name is not None:
        if not payload.display_name.strip():
            raise HTTPException(status_code=400, detail="Display name cannot be empty")
        user.display_name = payload.display_name.strip()
    if payload.hide_community_from_non_friends is not None:
        user.hide_community_from_non_friends = payload.hide_community_from_non_friends
    db.commit()
    return _serialize_user(user, user, db)


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


def _serialize_post(post: Post, viewer: Optional[User], db: Session) -> Dict[str, Any]:
    community = db.get(Community, post.community_id) if post.community_id else None
    return {
        "id": post.id,
        "body": post.body,
        "visibility": post.visibility,
        "createdAt": post.created_at.isoformat(),
        "communityId": post.community_id,
        "communityName": community.name if community else None,
        "author": _serialize_user(post.author, viewer, db),
    }


@router.post("/posts", status_code=201)
def create_post(
    payload: PostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Post body cannot be empty")
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    post = Post(
        id=f"post-{uuid4().hex[:10]}",
        user_id=user.id,
        community_id=user.community_id,
        body=payload.body.strip(),
        visibility=payload.visibility,
        created_at=datetime.now(timezone.utc),
    )
    db.add(post)
    db.commit()
    return _serialize_post(post, user, db)


@router.get("/feed/city")
def city_feed(
    viewer: Optional[User] = Depends(_get_optional_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    posts = db.execute(
        select(Post)
        .where(Post.visibility == "public")
        .order_by(Post.created_at.desc())
        .limit(50)
    ).scalars().all()
    return [_serialize_post(p, viewer, db) for p in posts]


@router.get("/communities/{community_id}/feed")
def community_feed(
    community_id: str,
    viewer: Optional[User] = Depends(_get_optional_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    if not db.get(Community, community_id):
        raise HTTPException(status_code=404, detail="Community not found")
    is_member = viewer is not None and viewer.community_id == community_id
    query = select(Post).where(Post.community_id == community_id)
    if not is_member:
        query = query.where(Post.visibility == "public")
    posts = db.execute(query.order_by(Post.created_at.desc()).limit(50)).scalars().all()
    return [_serialize_post(p, viewer, db) for p in posts]
