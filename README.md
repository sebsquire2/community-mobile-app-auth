# community-mobile-app-auth

## Problem

Implementing authentication and tiered authorisation to content (where the same content is visible or hidden depending on a user's group membership) without sacrificing session smoothness or introducing security shortcuts.

## What this is 

A mobile app with full working authentication and authorisation for users in different small communities sharing the same base community (city in this case) use case - the same piece of content is visible or invisible depending on who's asking
Showcases:
 - Users can browse the city feed and see public posts from all groups, or their community feed to see just posts from their community.
 - A user's community membership can be hidden from strangers.
 - Users can switch communities, switching their posting and viewing context at the same time.

## Screenshots

<table>
  <tr>
    <td align="center">
      <img src="docs/screenshots/Screenshot%20from%202026-05-03%2017-56-07.png" alt="Login flow screenshot 1" width="180" />
    </td>
    <td align="center">
      <img src="docs/screenshots/Screenshot%20from%202026-05-03%2017-56-27.png" alt="Login flow screenshot 2" width="180" />
    </td>
    <td align="center">
      <img src="docs/screenshots/Screenshot%20from%202026-05-03%2017-57-07.png" alt="App screenshot 1" width="180" />
    </td>
    <td align="center">
      <img src="docs/screenshots/Screenshot%20from%202026-05-03%2017-57-13.png" alt="App screenshot 2" width="180" />
    </td>
  </tr>
</table>

## Run

````bash
make docker-up    # run backend + db
make dev-frontend
# App at http://localhost:8081 · API at http://localhost:8000 · Swagger at http://localhost:8000/docs 
make migrate      # apply DB migrations
make test         # run tests
````

## Demo users

Password: `password123`.

| Email | Username |
|---|---|
| alice@example.com | alice |
| bob@example.com | bob |
| carol@example.com | carol |
| dave@example.com | dave |
| eve@example.com | eve |
| frank@example.com | frank |

---

## Architecture

Production-quality authentication system extracted from a React Native social app. Full stack: FastAPI backend + Expo (React Native) frontend.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy · PostgreSQL · Alembic · PyJWT · Argon2id · slowapi · React Native · Expo · TypeScript

| Area | Files | What it does |
|---|---|---|
| JWT + token logic | `backend/security/auth.py` | Issue/verify JWTs, hash/rotate refresh tokens |
| Email rate limiting | `backend/security/auth_rate_limit.py` | Per-email brute-force protection |
| Auth endpoints | `backend/api/auth_routes.py` | login, register, refresh, logout, admin revoke |
| Request schemas | `backend/api/schemas.py` | Pydantic models for all auth endpoints |
| HTTP client | `frontend/lib/api.ts` | Token management, refresh mutex, retry-on-401 |
| Session context | `frontend/lib/session.tsx` | React context, session lifecycle |
| Token storage | `frontend/lib/sessionStore.ts` | SecureStore (keychain) + AsyncStorage split |
| Session events | `frontend/lib/sessionInvalidation.ts` | Pub/sub event bus for forced logout |
| Login UI | `frontend/app/login.tsx` | Email/password login and registration |
| Route protection | `frontend/app/_layout.tsx` | AuthGate — redirects unauthenticated users |

---

## Design decisions and why

### 1. Hybrid JWT + rotating opaque refresh tokens

**Problem:** Pure JWT can't revoke tokens without extra server-side state. Pure sessions require a DB lookup on every request.

**Solution:** Short-lived JWT access tokens (15 min) paired with long-lived opaque refresh tokens (7 days, stored as SHA-256 hashes in the DB, revocable immediately). Access tokens carry a `token_version` that is checked against the user row so logout/revocation can invalidate them immediately.

- Access token validation = verify JWT, then compare `token_version` to the user row
- Logout/revocation = revoke the refresh token and increment `token_version`
- Stolen session = detectable within 7 days (or immediately if the token is used)

### 2. Argon2id instead of bcrypt

Argon2id is memory-hard. An attacker who leaks the DB and tries to brute-force offline faces GPU/ASIC resistance because each attempt requires a full memory allocation (default: 64 MiB). bcrypt only provides time-hardness — modern GPUs crack it at ~1 billion hashes/sec.

### 3. The concurrent refresh problem — and why a mutex fixes it

**Problem:** When an access token expires, 4 parallel in-flight requests all get 401 simultaneously. A naive fix: each request independently calls `/auth/refresh` would break immediately: the first call rotates the refresh token, so calls 2-4 present a revoked token and get 401 again. The client looks "logged out" for no reason.

**Solution has two parts:**

**Server:** `SELECT FOR UPDATE` row lock ensures only one concurrent refresh call can succeed with a given token. The second caller sees `revoked_at` is already set and gets 401.

**Client:** a promise mutex ensures only one refresh call is in-flight at a time. All other pending requests wait on the same promise:

Defense in depth: server-side lock prevents replay attacks from multiple devices, client-side mutex prevents the 401 storm from a single device.

### 4. Multi-layer rate limiting

**Problem:** An attacker targeting a specific account will rotate IPs to bypass IP-based limits.

- **IP-based (slowapi):** 10/min on `/auth/login`, 5/min on `/auth/register` — blocks untargeted attacks
- **Per-email (DB-backed):** 10 failures per 15-minute window — applies regardless of source IP

Scaling note: per-email table works fine for single-server deployments, multi-container would need Redis.

### 5. Token storage on mobile

| Token | Storage | Reason |
|---|---|---|
| Access token | In-memory only (`let accessToken`) | Ephemeral; never survives app restart |
| Refresh token | `expo-secure-store` (iOS Keychain / Android Keystore) | Hardware-backed encrypted storage |
| User metadata | `AsyncStorage` | Not sensitive; fast to read on app launch |

On app restart user metadata loads from AsyncStorage immediately (fast UI), then the access token is obtained by calling `/auth/refresh` in the background. The access token is never persisted to disk.

### 6. Fail-fast environment validation

The system refuses to start if misconfigured meaning no silent insecure defaults in production.

### 7. Viewer permissions — data withheld server-side

Privacy settings (`hide_community_from_non_friends`) are enforced in the serializer, not the UI. Sensitive fields are nulled out server side. The client is told the viewer's relationship (`self`, `friend`, `follower`, `stranger`) so it can render correctly but never receives data it isn't entitled to.

---

## Known limitations / pre-production TODOs

These are documented intentionally — they represent recognised trade-offs, not oversights:

1. **No email verification on registration**: `validate_email()` checks format only, we should check deliverability.
2. **No input length limits**: no max length on display name, email, etc.
