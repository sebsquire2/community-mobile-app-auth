from __future__ import annotations

import concurrent.futures

import pytest

from backend.security.auth import hash_password, issue_tokens_for_user
from backend.models import Community, User


def _make_user(db, *, email="user@example.com", password="password123", community_id=None) -> User:
    user = User(
        id=f"user-{email[:8].replace('@', '')}",
        username=email.split("@")[0],
        email=email,
        password_hash=hash_password(password),
        display_name="Test User",
        community_id=community_id,
    )
    db.add(user)
    db.commit()
    return user


class TestRegister:
    def test_register_success(self, client, default_community):
        r = client.post("/auth/register", json={
            "email": "new@example.com",
            "password": "password123",
            "displayName": "New User",
        })
        assert r.status_code == 201
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["user"]["id"].startswith("user-")

    def test_register_duplicate_email(self, client, db, default_community):
        _make_user(db, email="existing@example.com")
        r = client.post("/auth/register", json={
            "email": "existing@example.com",
            "password": "password123",
            "displayName": "Another",
        })
        assert r.status_code == 409

    def test_register_short_password(self, client, default_community):
        r = client.post("/auth/register", json={
            "email": "short@example.com",
            "password": "abc",
            "displayName": "Short",
        })
        assert r.status_code == 400

    def test_register_invalid_email(self, client):
        r = client.post("/auth/register", json={
            "email": "not-an-email",
            "password": "password123",
            "displayName": "Bad Email",
        })
        assert r.status_code == 400


class TestLogin:
    def test_login_success(self, client, db):
        _make_user(db, email="login@example.com", password="mypassword")
        r = client.post("/auth/login", json={"email": "login@example.com", "password": "mypassword"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client, db):
        _make_user(db, email="login2@example.com", password="correctpass")
        r = client.post("/auth/login", json={"email": "login2@example.com", "password": "wrongpass"})
        assert r.status_code == 401

    def test_login_unknown_email(self, client):
        r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "pass"})
        assert r.status_code == 401

    def test_oauth_account_rejects_password_login(self, client, db):
        user = User(
            id="user-oauthonly",
            username="oauthonly",
            email="oauth@example.com",
            password_hash=None,
            display_name="OAuth Only",
            oauth_provider="google",
            oauth_sub="google-sub-123",
        )
        db.add(user)
        db.commit()
        r = client.post("/auth/login", json={"email": "oauth@example.com", "password": "anything"})
        assert r.status_code == 400
        assert "Google" in r.json()["detail"]


class TestRefreshAndLogout:
    def test_refresh_rotates_tokens(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        r = client.post("/auth/refresh", json={"refresh_token": tokens.refresh_token})
        assert r.status_code == 200
        body = r.json()
        assert body["refresh_token"] != tokens.refresh_token
        assert body["access_token"] != tokens.access_token

    def test_used_refresh_token_rejected(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        client.post("/auth/refresh", json={"refresh_token": tokens.refresh_token})
        r = client.post("/auth/refresh", json={"refresh_token": tokens.refresh_token})
        assert r.status_code == 401

    def test_logout_invalidates_refresh_token(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        r = client.post(
            "/auth/logout",
            json={"refresh_token": tokens.refresh_token},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200
        r2 = client.post("/auth/refresh", json={"refresh_token": tokens.refresh_token})
        assert r2.status_code == 401

    def test_logout_invalidates_access_token_immediately(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)

        r = client.post(
            "/auth/logout",
            json={"refresh_token": tokens.refresh_token},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200

        r2 = client.get("/users/me", headers={"Authorization": f"Bearer {tokens.access_token}"})
        assert r2.status_code == 401

    def test_revoke_sessions_invalidates_existing_access_token(self, client, db, monkeypatch):
        monkeypatch.setattr("backend.core.dependencies.ADMIN_API_KEY", "test-admin-key")
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)

        r = client.post(
            "/auth/revoke-sessions",
            json={"user_id": user.id},
            headers={"X-Admin-Key": "test-admin-key"},
        )
        assert r.status_code == 200

        r2 = client.get("/users/me", headers={"Authorization": f"Bearer {tokens.access_token}"})
        assert r2.status_code == 401


class TestConcurrentRefresh:
    def test_only_one_concurrent_refresh_succeeds(self, db):
        """
        When two threads simultaneously present the same refresh token, exactly one
        must succeed and the other must get 401. The SELECT FOR UPDATE row lock in
        rotate_refresh_token() enforces this atomically.
        """
        from fastapi.testclient import TestClient
        from backend.main import app

        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        db.close()

        results = []

        def do_refresh():
            with TestClient(app) as c:
                r = c.post("/auth/refresh", json={"refresh_token": tokens.refresh_token})
                results.append(r.status_code)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(do_refresh), executor.submit(do_refresh)]
            concurrent.futures.wait(futures)

        assert sorted(results) == [200, 401], f"Expected one 200 and one 401, got {results}"


class TestRateLimiting:
    def test_email_rate_limit_triggers_after_10_failures(self, client, db):
        _make_user(db, email="target@example.com", password="correctpassword")
        for _ in range(10):
            client.post("/auth/login", json={"email": "target@example.com", "password": "wrong"})
        r = client.post("/auth/login", json={"email": "target@example.com", "password": "correctpassword"})
        assert r.status_code == 429


class TestGetMe:
    def test_get_me_returns_current_user(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        r = client.get("/users/me", headers={"Authorization": f"Bearer {tokens.access_token}"})
        assert r.status_code == 200
        assert r.json()["id"] == user.id

    def test_get_me_unauthenticated(self, client):
        r = client.get("/users/me")
        assert r.status_code == 401


def _make_community(db, *, id: str, name: str) -> Community:
    c = Community(id=id, name=name)
    db.add(c)
    db.commit()
    return c


class TestListCommunities:
    def test_returns_all_communities_with_member_counts(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        beta = _make_community(db, id="c-beta", name="Beta")
        _make_user(db, email="u1@x.com", community_id=alpha.id)
        _make_user(db, email="u2@x.com", community_id=alpha.id)
        _make_user(db, email="u3@x.com", community_id=beta.id)

        r = client.get("/communities")
        assert r.status_code == 200
        by_id = {c["id"]: c for c in r.json()}
        assert by_id["c-alpha"]["memberCount"] == 2
        assert by_id["c-beta"]["memberCount"] == 1

    def test_community_with_no_members_shows_zero(self, client, db):
        _make_community(db, id="c-empty", name="Empty")
        r = client.get("/communities")
        assert r.status_code == 200
        by_id = {c["id"]: c for c in r.json()}
        assert by_id["c-empty"]["memberCount"] == 0


class TestUpdateMe:
    def test_switch_community(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        beta = _make_community(db, id="c-beta", name="Beta")
        user = _make_user(db, community_id=alpha.id)
        tokens = issue_tokens_for_user(db, user)

        r = client.patch(
            "/users/me",
            json={"communityId": beta.id},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200
        assert r.json()["communityId"] == beta.id

    def test_community_counts_update_after_switch(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        beta = _make_community(db, id="c-beta", name="Beta")
        user = _make_user(db, community_id=alpha.id)
        tokens = issue_tokens_for_user(db, user)

        client.patch(
            "/users/me",
            json={"communityId": beta.id},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )

        r = client.get("/communities")
        by_id = {c["id"]: c for c in r.json()}
        assert by_id["c-alpha"]["memberCount"] == 0
        assert by_id["c-beta"]["memberCount"] == 1

    def test_switch_to_unknown_community_returns_404(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        r = client.patch(
            "/users/me",
            json={"communityId": "no-such-community"},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 404

    def test_update_display_name(self, client, db):
        user = _make_user(db)
        tokens = issue_tokens_for_user(db, user)
        r = client.patch(
            "/users/me",
            json={"displayName": "New Name"},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200
        assert r.json()["displayName"] == "New Name"

    def test_unauthenticated_patch_rejected(self, client):
        r = client.patch("/users/me", json={"displayName": "Hacker"})
        assert r.status_code == 401


class TestGetUser:
    def test_public_community_visible_to_stranger(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        target = _make_user(db, email="target@x.com", community_id=alpha.id)
        # target has hide_community_from_non_friends=False (default)

        viewer = _make_user(db, email="viewer@x.com")
        tokens = issue_tokens_for_user(db, viewer)

        r = client.get(
            f"/users/{target.id}",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200
        assert r.json()["communityId"] == alpha.id
        assert r.json()["viewerRelationship"] == "stranger"

    def test_hidden_community_not_visible_to_stranger(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        target = _make_user(db, email="target@x.com", community_id=alpha.id)
        target.hide_community_from_non_friends = True
        db.commit()

        viewer = _make_user(db, email="viewer@x.com")
        tokens = issue_tokens_for_user(db, viewer)

        r = client.get(
            f"/users/{target.id}",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert r.status_code == 200
        assert r.json()["communityId"] is None

    def test_unauthenticated_viewer_sees_public_community(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        target = _make_user(db, email="target@x.com", community_id=alpha.id)

        r = client.get(f"/users/{target.id}")
        assert r.status_code == 200
        assert r.json()["communityId"] == alpha.id

    def test_unauthenticated_viewer_cannot_see_hidden_community(self, client, db):
        alpha = _make_community(db, id="c-alpha", name="Alpha")
        target = _make_user(db, email="target@x.com", community_id=alpha.id)
        target.hide_community_from_non_friends = True
        db.commit()

        r = client.get(f"/users/{target.id}")
        assert r.status_code == 200
        assert r.json()["communityId"] is None

    def test_unknown_user_returns_404(self, client):
        r = client.get("/users/user-does-not-exist")
        assert r.status_code == 404
