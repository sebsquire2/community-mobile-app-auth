from __future__ import annotations

from fastapi import Header, HTTPException

from backend.core.config import ADMIN_API_KEY
from backend.core.db import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY not configured on this server")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")
