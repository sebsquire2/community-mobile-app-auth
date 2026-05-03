from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import IS_PROD_LIKE


def _rate_limit_key(request: Request) -> str:
    if IS_PROD_LIKE:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if first_ip:
                return first_ip
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)
