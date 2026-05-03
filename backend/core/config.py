from __future__ import annotations

import os


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS")
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


RAW_ENV = (os.getenv("ENV") or "").strip().lower()
_ALLOWED_ENVS = {"development", "dev", "test", "staging", "production", "prod"}
if not RAW_ENV or RAW_ENV not in _ALLOWED_ENVS:
    raise RuntimeError(
        "ENV must be explicitly set to one of: development, dev, test, staging, production, prod"
    )

IS_PROD = RAW_ENV in {"production", "prod"}
IS_PROD_LIKE = RAW_ENV in {"staging", "production", "prod"}

ENABLE_ADMIN_PANEL = _env_flag("ENABLE_ADMIN_PANEL", default=False)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
_DEV_ADMIN_SESSION_SECRET = "dev-admin-session-secret"
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", _DEV_ADMIN_SESSION_SECRET)

if IS_PROD and ADMIN_SESSION_SECRET == _DEV_ADMIN_SESSION_SECRET:
    raise RuntimeError(
        "ADMIN_SESSION_SECRET must not use the default value when ENV=production."
    )
if ENABLE_ADMIN_PANEL and not os.getenv("ADMIN_PASSWORD"):
    raise RuntimeError("ADMIN_PASSWORD must be set when ENABLE_ADMIN_PANEL=true")
if IS_PROD_LIKE and not ADMIN_API_KEY:
    raise RuntimeError(
        "ADMIN_API_KEY must be set when ENV is staging/production to protect admin operations"
    )

CORS_ALLOW_ORIGINS = _cors_allow_origins()
