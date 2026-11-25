import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_supabase_anon_client, log_supabase_auth_error
from app.models.academic import StudentProfile
from app.models.user import AccountStatus, User, UserRole


def supabase_user(access_token: str) -> Any:
    try:
        response = create_supabase_anon_client().auth.get_user(access_token)
        return response.user
    except Exception as exc:
        status_code, _ = log_supabase_auth_error("token-validation", exc)
        if status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable",
            ) from exc
        if status_code is None or status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc


def synchronized_user(db: Session, access_token: str) -> tuple[User, Any]:
    auth_user = supabase_user(access_token)
    auth_id = getattr(auth_user, "id", None)
    email = getattr(auth_user, "email", None)
    if not auth_id or not email:
        raise HTTPException(status_code=401, detail="Authenticated identity is incomplete")

    auth_uuid = uuid.UUID(str(auth_id))
    confirmed = getattr(auth_user, "email_confirmed_at", None) or getattr(
        auth_user, "confirmed_at", None
    )
    user = db.scalars(select(User).where(User.supabase_auth_id == auth_uuid)).first()
    if user is None:
        user = db.scalars(select(User).where(User.email == email.lower())).first()

    if user is None:
        raise HTTPException(
            status_code=403,
            detail="Profile not found. Complete registration first.",
        )

    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Account is inactive")
    if not confirmed:
        raise HTTPException(status_code=403, detail="Email verification is required")

    user.supabase_auth_id = auth_uuid
    user.email = email.lower()
    user.email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, auth_user


def require_role(user: User, role: UserRole) -> None:
    if user.role != role:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
