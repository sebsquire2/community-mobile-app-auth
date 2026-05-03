# community-mobile-app-auth

Production-quality authentication system extracted from a React Native social app. Full stack: FastAPI backend + Expo (React Native) frontend.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL · Alembic · PyJWT · Argon2id · slowapi · React Native · Expo · TypeScript

---

## What's here

| Area | Files | What it does |
|---|---|---|
| JWT + token logic | `backend/security/auth.py` | Issue/verify JWTs, hash/rotate refresh tokens |
| Email rate limiting | `backend/security/auth_rate_limit.py` | Per-email brute-force protection |
| Auth endpoints | `backend/api/auth_routes.py` | login, register, refresh, logout, OAuth, admin revoke |
| Request schemas | `backend/api/schemas.py` | Pydantic models for all auth endpoints |
| HTTP client | `frontend/lib/api.ts` | Token management, refresh mutex, retry-on-401 |
| Session context | `frontend/lib/session.tsx` | React context, session lifecycle |
| Token storage | `frontend/lib/sessionStore.ts` | SecureStore (keychain) + AsyncStorage split |
| Session events | `frontend/lib/sessionInvalidation.ts` | Pub/sub event bus for forced logout |
| Login UI | `frontend/app/login.tsx` | Email/password + Google + Apple |
| Route protection | `frontend/app/_layout.tsx` | AuthGate — redirects unauthenticated users |

---

## Quick start

```bash
# Backend
cp .env.example .env
docker-compose up -d db
uv pip install -e .
alembic -c backend/alembic.ini upgrade head
uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npx expo start
```

Or run everything with Docker:

```bash
docker-compose up
```

API available at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

---

## Running tests

```bash
createdb auth_showcase_test   # one-time setup
ENV=test pytest backend/tests/ -v
```

---

## Design decisions

### 1. Hybrid JWT + rotating opaque refresh tokens

**The problem:** Pure JWT can't revoke tokens — a logged-out user stays authenticated until expiry. Pure sessions require a DB lookup on every request.

**The solution:** Short-lived JWT access tokens (15 min, stateless) paired with long-lived opaque refresh tokens (7 days, stored as SHA-256 hashes in the DB, revocable immediately).

- Access token validation = zero DB cost
- Logout/revocation = flip `revoked_at` in one row
- Stolen session = detectable within 7 days (or immediately if the token is used)

```python
# backend/security/auth.py
def rotate_refresh_token(db, raw_refresh_token):
    with db.begin():
        token_row = db.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw_refresh_token))
            .with_for_update()          # serialise concurrent refresh calls
        ).scalar_one_or_none()
        token_row.revoked_at = now      # single-use: old token is dead immediately
        new_refresh = generate_refresh_token()
        _create_refresh_token_row(db, user_id, new_refresh)
```

### 2. Argon2id over bcrypt

Argon2id is memory-hard. An attacker who leaks the DB and tries to brute-force offline faces GPU/ASIC resistance because each attempt requires a full memory allocation (default: 64 MiB). bcrypt only provides time-hardness — modern GPUs crack it at ~1 billion hashes/sec.

Parameters are tunable via env vars without code changes:

```
ARGON2_TIME_COST=3
ARGON2_MEMORY_COST_KIB=65536   # 64 MiB
ARGON2_PARALLELISM=2
```

### 3. The concurrent refresh problem — and why a mutex fixes it

When an access token expires, 4 parallel in-flight requests all get 401 simultaneously. A naive fix — each request independently calls `/auth/refresh` — breaks immediately: the first call rotates the refresh token, so calls 2-4 present a revoked token and get 401 again. The client looks "logged out" for no reason.

**Fix has two parts:**

**Server side** — `SELECT FOR UPDATE` row lock ensures only one concurrent refresh call can succeed with a given token. The second caller sees `revoked_at` is already set and gets 401.

**Client side** — a promise mutex ensures only one refresh call is in-flight at a time. All other pending requests wait on the same promise:

```typescript
// frontend/lib/api.ts
async function getValidAccessToken() {
  const existing = await loadAccessTokenFromStorage();
  if (existing) return existing;
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => { refreshPromise = null; });
  }
  return refreshPromise;   // all callers share this — one network call, not N
}
```

This is defense in depth: server-side lock prevents replay attacks from multiple *devices*; client-side mutex prevents the 401 storm from a single device.

### 4. Multi-layer rate limiting

An attacker targeting a specific account will rotate IPs to bypass IP-based limits. Two layers:

- **IP-based (slowapi):** 10/min on `/auth/login`, 5/min on `/auth/register` — blocks untargeted attacks
- **Per-email (DB-backed):** 10 failures per 15-minute window — applies regardless of source IP

```python
# backend/security/auth_rate_limit.py
def check_email_rate_limit(db, email):
    # Cleans up old entries, counts recent failures, raises 429 if >= threshold
```

Scaling note: the per-email table works fine for single-server deployments. Multi-container would need Redis. This is intentionally documented, not papered over.

### 5. OAuth account linking (Google + Apple)

Three-stage merge strategy when an OAuth login arrives:

1. **Exact match on `(provider, sub)`** — returning OAuth user, fast path
2. **Email match** — user created a password account then signed in with OAuth; we link the provider instead of creating a duplicate account
3. **Create new user** — genuinely new, assign to the default community

```python
def _find_or_create_oauth_user(db, *, provider, sub, email, display_name):
    # Stage 1: exact provider+sub match
    # Stage 2: email match → link provider to existing account
    # Stage 3: create new user
```

### 6. Token storage on mobile

| Token | Storage | Reason |
|---|---|---|
| Access token | In-memory only (`let accessToken`) | Ephemeral; never survives app restart |
| Refresh token | `expo-secure-store` (iOS Keychain / Android Keystore) | Hardware-backed encrypted storage |
| User metadata | `AsyncStorage` | Not sensitive; fast to read on app launch |

On app restart: user metadata loads from AsyncStorage immediately (fast UI), then the access token is obtained by calling `/auth/refresh` in the background. The access token is never persisted to disk.

On web: `expo-secure-store` is unavailable; both tokens fall back to `localStorage`. This is acceptable for demo/web builds.

### 7. Fail-fast environment validation

The system refuses to start if misconfigured:

```python
# Startup fails hard if:
# - ENV is not set or not a recognised value
# - ENV=staging/production and JWT_SECRET is unset
# - ENV=production and ADMIN_SESSION_SECRET is still the dev default
# - ENV=staging/production and ADMIN_API_KEY is unset
```

No silent insecure defaults in production. A missing secret causes startup failure, not a degraded state.

### 8. Viewer permissions — data withheld server-side

Privacy settings (`hide_community_from_non_friends`) are enforced in the serializer, not the UI. Sensitive fields are nulled out before the response leaves the server. The client is told the viewer's relationship (`self`, `friend`, `follower`, `stranger`) so it can render correctly, but it never receives data it isn't entitled to.

```python
def _serialize_user(user, viewer, db):
    relationship = _viewer_relationship(viewer, user, db)
    can_see_community = relationship in ("self", "friend") or not user.hide_community_from_non_friends
    return ApiUser(community_id=user.community_id if can_see_community else None, ...)
```

---

## Known limitations / pre-production TODOs

These are documented intentionally — they represent recognised trade-offs, not oversights:

1. **15-minute window after logout** — the access token remains valid until expiry after `/auth/logout`. The refresh token is revoked immediately; a stolen access token has at most 15 minutes of validity.
2. **Per-email rate limiting is in-memory via DB rows** — works for single-server deployments; needs Redis for horizontal scaling.
3. **No email verification on registration** — `validate_email()` checks format only; it does not confirm deliverability. Add email confirmation before production.
4. **No input length limits** — no max length on display name, email, etc. Add these before production.
