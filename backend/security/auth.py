from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import SessionLocal
from backend.models import RefreshToken, User

_RAW_ENV = (os.getenv("ENV") or "").strip().lower()
_ALLOWED_ENVS = {"development", "dev", "test", "staging", "production", "prod"}
if not _RAW_ENV or _RAW_ENV not in _ALLOWED_ENVS:
    raise RuntimeError(
        "ENV must be explicitly set to one of: development, dev, test, staging, production, prod"
    )
_IS_PROD_LIKE = _RAW_ENV in {"staging", "production", "prod"}
_IS_DEV_OR_TEST = _RAW_ENV in {"development", "dev", "test"}

# Fail fast outside local dev/test if JWT_SECRET is not explicitly configured.
if _IS_PROD_LIKE and not os.getenv("JWT_SECRET"):
    raise RuntimeError(
        "JWT_SECRET environment variable must be set when ENV is staging/production. "
        "Configure it via your secrets manager / task definition environment variables."
    )

DEFAULT_DEV_JWT_SECRET = "dev-insecure-secret-change-me-32bytes+"

# Argon2id parameters are tunable via env vars. Defaults balance security and
# login latency (~200-300ms). Increase time_cost/memory_cost for higher security
# at the cost of longer logins.
_password_hasher = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST_KIB", "65536")),
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "2")),
)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def jwt_secret() -> str:
    configured = os.getenv("JWT_SECRET")
    if configured:
        return configured
    if _IS_DEV_OR_TEST:
        return DEFAULT_DEV_JWT_SECRET
    raise RuntimeError("JWT_SECRET must be configured outside local dev/test")


def jwt_algorithm() -> str:
    return "HS256"


def access_token_expire_minutes() -> int:
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))


def refresh_token_expire_days() -> int:
    return int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _password_hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: str) -> str:
    now = _utcnow()
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=access_token_expire_minutes())).timestamp()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm=jwt_algorithm())


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[jwt_algorithm()])
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token")
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return subject


def generate_refresh_token() -> str:
    return secrets.token_hex(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_refresh_token_row(db: Session, user_id: str, raw_token: str) -> RefreshToken:
    now = _utcnow()
    row = RefreshToken(
        id=f"rt-{secrets.token_hex(12)}",
        user_id=user_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + timedelta(days=refresh_token_expire_days()),
        created_at=now,
        revoked_at=None,
    )
    db.add(row)
    return row


def issue_tokens_for_user(db: Session, user: User) -> AuthTokens:
    raw_refresh_token = generate_refresh_token()
    _create_refresh_token_row(db, user.id, raw_refresh_token)
    db.commit()
    return AuthTokens(access_token=create_access_token(user.id), refresh_token=raw_refresh_token)


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> tuple[AuthTokens, str]:
    """
    Atomically revoke the presented refresh token and issue a new token pair.

    Uses SELECT FOR UPDATE to serialize concurrent refresh requests from multiple
    devices. If the token has already been revoked, a second device (or attacker)
    presenting the same token gets 401 — forcing re-authentication.
    """
    token_hash = hash_refresh_token(raw_refresh_token)
    now = _utcnow()

    user_id: Optional[str] = None
    new_refresh: Optional[str] = None
    with db.begin():
        token_row = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        ).scalar_one_or_none()
        if not token_row:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if token_row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Refresh token already used")
        if token_row.expires_at <= now:
            raise HTTPException(status_code=401, detail="Refresh token expired")

        token_row.revoked_at = now
        user_id = token_row.user_id
        new_refresh = generate_refresh_token()
        _create_refresh_token_row(db, user_id, new_refresh)

    assert user_id is not None and new_refresh is not None
    tokens = AuthTokens(access_token=create_access_token(user_id), refresh_token=new_refresh)
    return tokens, user_id


def revoke_refresh_token(db: Session, user_id: str, raw_refresh_token: str) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    with db.begin():
        token_row = db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user_id)
            .with_for_update()
        ).scalar_one_or_none()
        if token_row and token_row.revoked_at is None:
            token_row.revoked_at = _utcnow()


def get_auth_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_auth_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
