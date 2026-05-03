from __future__ import annotations

import time

import pytest

from backend.security.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    issue_tokens_for_user,
    rotate_refresh_token,
    verify_password,
)
from backend.models import User


def _make_user(db, *, email="test@example.com", password="password123") -> User:
    user = User(
        id="user-test0001",
        username="testuser",
        email=email,
        password_hash=hash_password(password),
        display_name="Test User",
    )
    db.add(user)
    db.commit()
    return user


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = hash_password("mysecret")
        assert "mysecret" not in h

    def test_correct_password_verifies(self):
        h = hash_password("mysecret")
        assert verify_password("mysecret", h)

    def test_wrong_password_fails(self):
        h = hash_password("mysecret")
        assert not verify_password("wrongpassword", h)

    def test_empty_hash_fails(self):
        assert not verify_password("anything", "")

    def test_two_hashes_differ(self):
        # Argon2 uses a random salt per hash
        assert hash_password("same") != hash_password("same")


class TestJWT:
    def test_valid_token_roundtrips(self):
        token = create_access_token("user-abc123")
        assert decode_access_token(token) == "user-abc123"

    def test_tampered_token_rejected(self):
        from fastapi import HTTPException
        token = create_access_token("user-abc123")
        tampered = token[:-4] + "xxxx"
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered)
        assert exc_info.value.status_code == 401

    def test_wrong_type_rejected(self):
        import jwt as pyjwt
        from fastapi import HTTPException
        from backend.security.auth import jwt_secret, jwt_algorithm
        import time
        payload = {"sub": "user-abc", "type": "refresh", "iat": int(time.time()), "exp": int(time.time()) + 900}
        token = pyjwt.encode(payload, jwt_secret(), algorithm=jwt_algorithm())
        with pytest.raises(HTTPException):
            decode_access_token(token)


class TestRefreshTokenRotation:
    def test_rotation_issues_new_tokens(self, db):
        user = _make_user(db)
        original = issue_tokens_for_user(db, user)
        new_tokens, user_id = rotate_refresh_token(db, original.refresh_token)
        assert new_tokens.access_token != original.access_token
        assert new_tokens.refresh_token != original.refresh_token
        assert user_id == user.id

    def test_token_hash_stored_not_raw(self, db):
        from backend.models import RefreshToken
        from sqlalchemy import select
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        row = db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id)).scalar_one()
        assert row.token_hash != tokens.refresh_token
        assert row.token_hash == hash_refresh_token(tokens.refresh_token)

    def test_replay_attack_rejected(self, db):
        from fastapi import HTTPException
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        rotate_refresh_token(db, tokens.refresh_token)
        # Presenting the same token again (replay) must be rejected
        with pytest.raises(HTTPException) as exc_info:
            rotate_refresh_token(db, tokens.refresh_token)
        assert exc_info.value.status_code == 401
        assert "already used" in exc_info.value.detail

    def test_invalid_token_rejected(self, db):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            rotate_refresh_token(db, "deadbeef" * 12)
        assert exc_info.value.status_code == 401
