from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

_MAX_FAILED_LOGINS = 10
_FAILED_LOGIN_WINDOW = 15 * 60


def check_email_rate_limit(db: Session, email: str) -> None:
    """
    Enforce a per-email brute-force limit: 10 failed attempts per 15-minute window.

    Complements IP-based rate limiting (slowapi). An attacker rotating IPs can
    bypass IP limits, but per-email limits apply regardless of source address.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_FAILED_LOGIN_WINDOW)
    db.execute(
        text(
            """
            DELETE FROM auth_failed_login_attempts
            WHERE email = :email AND failed_at <= :cutoff
            """
        ),
        {"email": email, "cutoff": cutoff},
    )
    count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM auth_failed_login_attempts
            WHERE email = :email AND failed_at > :cutoff
            """
        ),
        {"email": email, "cutoff": cutoff},
    ).scalar_one()
    if count >= _MAX_FAILED_LOGINS:
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again in 15 minutes.",
        )


def record_failed_login(db: Session, email: str) -> None:
    db.execute(
        text(
            """
            INSERT INTO auth_failed_login_attempts (email, failed_at)
            VALUES (:email, :failed_at)
            """
        ),
        {"email": email, "failed_at": datetime.now(timezone.utc)},
    )
    db.commit()


def clear_login_attempts(db: Session, email: str) -> None:
    db.execute(
        text("DELETE FROM auth_failed_login_attempts WHERE email = :email"),
        {"email": email},
    )
    db.commit()
