import hmac
import uuid
from collections import defaultdict
from time import monotonic

from fastapi import Header, HTTPException, status
from supabase import Client, create_client

from app.core.config import settings


_rate_windows: dict[str, list[float]] = defaultdict(list)


def validate_student_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized.endswith("@rvce.edu.in"):
        raise HTTPException(status_code=400, detail="Student email must end with @rvce.edu.in")
    local = normalized[:-12]
    if not local or "+" in local or "@" in local:
        raise HTTPException(status_code=400, detail="Invalid RVCE email format")
    return normalized


def normalize_admin_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=400, detail="Invalid email address")
    return normalized


def create_supabase_anon_client() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY.",
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def create_supabase_service_client() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Server-side Supabase administration is not configured.",
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def verify_bootstrap_token(token: str) -> None:
    if not settings.ADMIN_BOOTSTRAP_TOKEN or not hmac.compare_digest(
        token, settings.ADMIN_BOOTSTRAP_TOKEN
    ):
        raise HTTPException(status_code=403, detail="Invalid administrator bootstrap token")


def rate_limit(key: str, limit: int = 5, window_seconds: int = 300) -> None:
    now = monotonic()
    events = _rate_windows[key]
    _rate_windows[key] = [timestamp for timestamp in events if now - timestamp < window_seconds]
    if len(_rate_windows[key]) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests; try again later")
    _rate_windows[key].append(now)


def bearer_token(authorization: str = Header(...)) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
        )
    return token.strip()
