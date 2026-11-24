from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.security import bearer_token
from app.database.connection import get_db
from app.models.user import User, UserRole
from app.services.auth import require_role, synchronized_user


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the Supabase identity and return the application user record.

    The database role is always authoritative; a role supplied by the client is
    never trusted.
    """
    token = bearer_token(authorization)
    user, _ = synchronized_user(db, token)
    return user


def require_student(user: User = Depends(get_current_user)) -> User:
    require_role(user, UserRole.STUDENT)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    require_role(user, UserRole.ADMIN_FACULTY)
    return user
