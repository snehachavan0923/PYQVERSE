import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import normalize_admin_email, validate_password_strength
from app.models.bootstrap import AdministratorBootstrapRecord
from app.models.user import AccountStatus, User, UserRole


class ProvisioningError(Exception):
    """Raised when a trusted administrator provisioning request cannot proceed."""


def _auth_user_from_response(response):
    return getattr(response, "user", None) or response


def _find_auth_user(client, email: str):
    try:
        users = client.auth.admin.list_users()
    except Exception:
        return None
    if hasattr(users, "users"):
        users = users.users
    for item in users or []:
        if str(getattr(item, "email", "")).lower() == email:
            return item
    return None


def _validate_credentials(email: str, password: str) -> tuple[str, str]:
    try:
        normalized_email = normalize_admin_email(email)
    except HTTPException as exc:
        raise ProvisioningError(str(exc.detail)) from exc
    try:
        validate_password_strength(password)
    except HTTPException as exc:
        raise ProvisioningError(str(exc.detail)) from exc
    return normalized_email, password


def provision_admin(
    db: Session,
    client,
    *,
    email: str,
    full_name: str,
    password: str,
) -> dict:
    """Create exactly one ADMIN_FACULTY account and its linked application record.

    This function never logs or persists the plaintext password.
    """
    normalized_email, _ = _validate_credentials(email, password)
    display_name = (full_name or "").strip() or normalized_email

    # Prevent concurrent command invocations from both observing an empty admin set.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 0x50595156})

    existing_admins = db.scalars(select(User).where(User.role == UserRole.ADMIN_FACULTY)).all()
    if existing_admins:
        same_email = next((item for item in existing_admins if item.email == normalized_email), None)
        if same_email is not None and len(existing_admins) == 1:
            return {
                "status": "already_provisioned",
                "user_id": str(same_email.id),
                "email": same_email.email,
                "role": same_email.role.value,
            }
        raise ProvisioningError(
            "An ADMIN_FACULTY account already exists. Remove or migrate the existing "
            "administrator before provisioning another one."
        )

    local_user = db.scalars(select(User).where(User.email == normalized_email)).first()

    metadata = {"full_name": display_name, "role": UserRole.ADMIN_FACULTY.value}
    auth_user = None
    try:
        response = client.auth.admin.create_user({
            "email": normalized_email,
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata,
        })
        auth_user = _auth_user_from_response(response)
    except Exception as create_error:
        auth_user = _find_auth_user(client, normalized_email)
        if auth_user is None:
            raise ProvisioningError(
                "Supabase Auth could not create the administrator identity. "
                "Check the service-role configuration and Supabase logs."
            ) from create_error
        auth_id = getattr(auth_user, "id", None)
        if not auth_id:
            raise ProvisioningError("The existing Supabase identity is missing an ID")
        try:
            client.auth.admin.update_user_by_id(
                auth_id,
                {
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": metadata,
                },
            )
        except Exception as update_error:
            raise ProvisioningError(
                "The existing Supabase identity could not be updated safely."
            ) from update_error

    auth_id = getattr(auth_user, "id", None)
    if not auth_id:
        raise ProvisioningError("Supabase did not return a usable administrator identity")
    auth_uuid = uuid.UUID(str(auth_id))

    if local_user is None:
        local_user = User(
            supabase_auth_id=auth_uuid,
            full_name=display_name,
            email=normalized_email,
            email_verified=True,
            role=UserRole.ADMIN_FACULTY,
            account_status=AccountStatus.ACTIVE,
        )
        db.add(local_user)
        status = "created"
    else:
        local_user.supabase_auth_id = auth_uuid
        local_user.full_name = display_name
        local_user.email = normalized_email
        local_user.email_verified = True
        local_user.role = UserRole.ADMIN_FACULTY
        local_user.account_status = AccountStatus.ACTIVE
        status = "updated"

    db.flush()

    record = db.scalars(
        select(AdministratorBootstrapRecord).where(
            AdministratorBootstrapRecord.email == normalized_email
        )
    ).first()
    if record is None:
        record = AdministratorBootstrapRecord(email=normalized_email)
        db.add(record)
    record.supabase_auth_id = auth_uuid
    record.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.flush()

    db.commit()
    db.refresh(local_user)

    if local_user.role != UserRole.ADMIN_FACULTY:
        raise ProvisioningError("Administrator role verification failed")
    if local_user.supabase_auth_id != auth_uuid:
        raise ProvisioningError("Administrator identity link verification failed")

    return {
        "status": status,
        "user_id": str(local_user.id),
        "email": local_user.email,
        "role": local_user.role.value,
    }
