import logging
import re
from collections import defaultdict
from time import monotonic

from fastapi import Header, HTTPException, status
from email_validator import EmailNotValidError, validate_email
from supabase import Client, create_client

from app.core.config import settings


_rate_windows: dict[str, list[float]] = defaultdict(list)
logger = logging.getLogger(__name__)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


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
    try:
        normalized = validate_email(normalized, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise HTTPException(status_code=400, detail="Invalid email address")
    return normalized


def validate_password_strength(password: str) -> str:
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(
            status_code=400,
            detail="Password must be between 8 and 128 characters",
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="Password must include an uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="Password must include a lowercase letter")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must include a number")
    return password


def log_supabase_auth_error(operation: str, exc: Exception) -> tuple[int | None, str | None]:
    """Log only Supabase's safe error metadata; never stringify the exception."""
    raw_status = getattr(exc, "status", None)
    status_code = raw_status if isinstance(raw_status, int) else None
    raw_code = getattr(exc, "code", None)
    code = (
        raw_code
        if isinstance(raw_code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", raw_code)
        else None
    )
    message = getattr(exc, "message", None)
    if not isinstance(message, str) or not message:
        message = "Supabase request failed"

    for secret in (
        settings.SUPABASE_ANON_KEY,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    ):
        if secret:
            message = message.replace(secret, "[redacted]")
    message = _JWT_PATTERN.sub("[redacted-token]", message)
    message = _EMAIL_PATTERN.sub("[redacted-email]", message)
    message = re.sub(
        r'''(?i)["']?\b(password|otp|token|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|authorization)["']?\s*[:=]\s*["']?(?:bearer\s+)?[^,\s}"']+''',
        r"\1=[redacted]",
        message,
    )
    message = re.sub(r"(?i)\b(authorization)\s+bearer\s+\S+", r"\1=[redacted]", message)
    message = re.sub(r"\b\d{6,10}\b", "[redacted-code]", message)
    message = " ".join(message.split())[:240]

    logger.warning(
        "Supabase auth request failed operation=%s exception_class=%s status=%s code=%s message=%s",
        operation,
        type(exc).__name__,
        status_code if status_code is not None else "unknown",
        code or "unknown",
        message,
    )
    return status_code, code


def registration_error_response(exc: Exception) -> HTTPException:
    status_code, code = log_supabase_auth_error("signup", exc)
    normalized_code = (code or "").lower()
    if normalized_code in {"user_already_exists", "email_exists", "user_exists"}:
        return HTTPException(
            status_code=409,
            detail="An account with this email already exists or is pending verification.",
        )
    if status_code == 429 or "rate_limit" in normalized_code or "over_email_send_rate_limit" in normalized_code:
        return HTTPException(status_code=429, detail="Email signup is temporarily rate limited. Try again later.")
    if status_code is not None and status_code >= 500:
        return HTTPException(status_code=503, detail="Supabase Auth is temporarily unavailable.")
    return HTTPException(
        status_code=400,
        detail="Supabase rejected registration. Check Auth email settings and the backend's safe error log.",
    )


def create_supabase_anon_client() -> Client:
    if (
        not settings.SUPABASE_URL
        or not settings.SUPABASE_ANON_KEY
        or "YOUR_" in settings.SUPABASE_URL
        or "YOUR_" in settings.SUPABASE_ANON_KEY
    ):
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY.",
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def create_supabase_service_client() -> Client:
    if (
        not settings.SUPABASE_URL
        or not settings.SUPABASE_SERVICE_ROLE_KEY
        or "YOUR_" in settings.SUPABASE_URL
        or "YOUR_" in settings.SUPABASE_SERVICE_ROLE_KEY
    ):
        raise HTTPException(
            status_code=503,
            detail="Server-side Supabase administration is not configured.",
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def rate_limit(key: str, limit: int = 5, window_seconds: int = 300) -> None:
    now = monotonic()
    events = _rate_windows[key]
    _rate_windows[key] = [timestamp for timestamp in events if now - timestamp < window_seconds]
    if len(_rate_windows[key]) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests; try again later")
    _rate_windows[key].append(now)


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
        )
    return token.strip()
