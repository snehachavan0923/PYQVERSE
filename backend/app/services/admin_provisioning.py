import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from supabase_auth.errors import AuthApiError, UserDoesntExist

from app.core.config import (
    EXPECTED_STAGING_PROJECT_REF,
    EXPECTED_STAGING_SUPABASE_HOSTNAME,
    EXPECTED_STAGING_SUPABASE_URL,
    settings,
)
from app.core.security import (
    normalize_admin_email,
    validate_password_strength,
    validate_student_email,
)
from app.models.bootstrap import AdministratorBootstrapRecord
from app.models.user import AccountStatus, User, UserRole


class ProvisioningError(Exception):
    """Raised when a trusted administrator provisioning request cannot proceed."""


def _auth_user_from_response(response: Any) -> Any:
    return getattr(response, "user", None) or response


def _extract_auth_id(auth_user: Any) -> str:
    if auth_user is None:
        return ""
    auth_id = getattr(auth_user, "id", None)
    if not auth_id and isinstance(auth_user, dict):
        auth_id = auth_user.get("id")
    return str(auth_id).strip() if auth_id else ""


def _find_auth_user(client: Any, email: str) -> Any:
    target = email.lower().strip()
    admin_api = getattr(getattr(client, "auth", None), "admin", None)
    if admin_api is None or not hasattr(admin_api, "list_users"):
        raise ProvisioningError("Supabase service-role client admin API is unavailable")

    per_page = 50
    page = 1
    max_pages = 200

    try:
        while page <= max_pages:
            try:
                response = admin_api.list_users(page=page, per_page=per_page)
            except TypeError:
                # Client does not support pagination arguments (e.g. simple unit test mocks)
                if page > 1:
                    break
                response = admin_api.list_users()

            users = getattr(response, "users", response)
            if isinstance(users, dict):
                users = users.get("users", [])
            users_list = list(users or [])

            for item in users_list:
                item_email = str(
                    getattr(item, "email", None) or (item.get("email") if isinstance(item, dict) else "")
                ).lower().strip()
                if item_email == target:
                    return item

            # If fewer than per_page items were returned, we have reached the last page
            if len(users_list) < per_page:
                break
            page += 1
    except ProvisioningError:
        raise
    except Exception as exc:
        raise ProvisioningError(f"Supabase Auth query failed: {exc}") from exc

    return None


def _find_auth_user_by_id(client: Any, uid: str) -> Any:
    target_id = str(uid).strip().lower()
    admin_api = getattr(getattr(client, "auth", None), "admin", None)
    if admin_api is None:
        raise ProvisioningError("Supabase service-role client admin API is unavailable")

    # 1. Try get_user_by_id if available
    if hasattr(admin_api, "get_user_by_id"):
        try:
            response = admin_api.get_user_by_id(str(uid))
            user = getattr(response, "user", response)
            if user is not None:
                user_id = _extract_auth_id(user).lower()
                if user_id == target_id:
                    return user
        except Exception as exc:
            status = getattr(exc, "status", None)
            code = getattr(exc, "code", None)
            is_genuine_404 = (
                status == 404
                or code == "user_not_found"
                or isinstance(exc, UserDoesntExist)
            )
            if is_genuine_404:
                return None
            raise ProvisioningError(
                f"Supabase Auth lookup by ID failed due to API/network error: {type(exc).__name__}"
            ) from exc

    # 2. Complete page-by-page list_users pagination fallback
    per_page = 50
    page = 1
    max_pages = 200

    try:
        while page <= max_pages:
            try:
                response = admin_api.list_users(page=page, per_page=per_page)
            except TypeError:
                if page > 1:
                    break
                response = admin_api.list_users()

            users = getattr(response, "users", response)
            if isinstance(users, dict):
                users = users.get("users", [])
            users_list = list(users or [])

            for item in users_list:
                item_id = _extract_auth_id(item).lower()
                if item_id == target_id:
                    return item

            if len(users_list) < per_page:
                break
            page += 1
    except ProvisioningError:
        raise
    except Exception as exc:
        raise ProvisioningError(
            f"Supabase Auth lookup by ID failed during user listing: {type(exc).__name__}"
        ) from exc

    return None


def _is_valid_staging_database_target(host: str | None, username: str | None) -> bool:
    if not host:
        return False
    host = host.strip().lower()
    username = (username or "").strip().lower()

    # Direct database connection: host must match db.<project_ref>.supabase.co exactly
    if host == f"db.{EXPECTED_STAGING_PROJECT_REF}.supabase.co":
        return True

    # Pooler database connection: host must be pooler.supabase.com or a subdomain of it
    is_pooler = host == "pooler.supabase.com" or host.endswith(".pooler.supabase.com")
    if is_pooler:
        # Must have the staging project ref in the username, e.g. postgres.<project_ref>
        parts = username.split(".", 1)
        if len(parts) == 2 and parts[1] == EXPECTED_STAGING_PROJECT_REF:
            return True

    return False


def _verify_staging_database(db: Session) -> None:
    if not hasattr(db, "get_bind"):
        raise ProvisioningError(
            "Recovery mode refused: Database session has no get_bind() method to inspect active connection."
        )
    try:
        bind = db.get_bind()
    except Exception as exc:
        raise ProvisioningError(
            f"Recovery mode refused: Failed to inspect active database session bind: {type(exc).__name__}"
        ) from exc

    if bind is None:
        raise ProvisioningError(
            "Recovery mode refused: Active database session bind is None."
        )
    bind_url = getattr(bind, "url", None)
    if bind_url is None:
        raise ProvisioningError(
            "Recovery mode refused: Active database session bind has no URL."
        )
    if not _is_valid_staging_database_target(bind_url.host, bind_url.username):
        raise ProvisioningError(
            f"Recovery mode refused: Active database session bind does not belong to the expected "
            f"staging project ('{EXPECTED_STAGING_PROJECT_REF}'). Production and non-staging "
            f"database recovery is strictly prohibited."
        )

    cfg_url = str(getattr(settings, "DATABASE_URL", "") or "").strip()
    if not cfg_url:
        raise ProvisioningError(
            "Recovery mode refused: DATABASE_URL configuration is missing."
        )
    try:
        parsed_cfg = make_url(cfg_url)
    except Exception as exc:
        raise ProvisioningError(
            "Recovery mode refused: Malformed DATABASE_URL configuration."
        ) from exc
    if not _is_valid_staging_database_target(parsed_cfg.host, parsed_cfg.username):
        raise ProvisioningError(
            f"Recovery mode refused: Configured DATABASE_URL does not belong to the expected "
            f"staging project ('{EXPECTED_STAGING_PROJECT_REF}'). Production and non-staging "
            f"database recovery is strictly prohibited."
        )


def _normalize_supabase_endpoint(url_val: Any) -> str:
    if not url_val:
        return ""
    try:
        raw_str = str(url_val).strip()
        parsed = urlparse(raw_str)
        if parsed.scheme != "https":
            return ""
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return ""
        path = (parsed.path or "").rstrip("/")
        if path:
            return ""
        if parsed.port and parsed.port != 443:
            return ""
        return f"https://{hostname}"
    except Exception:
        return ""


def _verify_staging_supabase_url(client: Any) -> None:
    cfg_raw = getattr(settings, "SUPABASE_URL", "")
    cfg_endpoint = _normalize_supabase_endpoint(cfg_raw)
    if not cfg_endpoint:
        raise ProvisioningError(
            "Recovery mode refused: Malformed or missing SUPABASE_URL configuration."
        )
    if cfg_endpoint != EXPECTED_STAGING_SUPABASE_URL:
        raise ProvisioningError(
            f"Recovery mode refused: Configured SUPABASE_URL host does not match the expected "
            f"staging Supabase host ({EXPECTED_STAGING_SUPABASE_HOSTNAME}). "
            f"Production, custom domains, and non-staging recovery are strictly prohibited."
        )

    client_raw = getattr(client, "supabase_url", None)
    if client_raw is None:
        raise ProvisioningError(
            "Recovery mode refused: Unable to inspect Supabase service client destination URL."
        )
    client_endpoint = _normalize_supabase_endpoint(client_raw)
    if not client_endpoint:
        raise ProvisioningError(
            "Recovery mode refused: Malformed Supabase service client destination URL."
        )
    if client_endpoint != EXPECTED_STAGING_SUPABASE_URL:
        raise ProvisioningError(
            f"Recovery mode refused: Supabase service client host does not match the expected "
            f"staging Supabase host ({EXPECTED_STAGING_SUPABASE_HOSTNAME})."
        )
    if client_endpoint != cfg_endpoint:
        raise ProvisioningError(
            "Recovery mode refused: Supabase service client URL and configured SUPABASE_URL mismatch."
        )


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
    client: Any,
    *,
    email: str,
    full_name: str,
    password: str,
    reset_password: bool = False,
) -> dict[str, str]:
    """Create or repair exactly one ADMIN_FACULTY account and its linked application record.

    Rules:
    1. If the existing PostgreSQL ADMIN_FACULTY record is correctly linked to the existing
       Supabase Auth identity:
       - Do not change the existing password.
       - Do not unnecessarily update the identity.
       - Return already_provisioned.
    2. If the PostgreSQL admin exists but has no Supabase Auth identity:
       - Create the missing Auth identity using the entered password.
       - Link the new Auth UUID to the existing PostgreSQL record.
    3. If a Supabase Auth identity exists but the PostgreSQL admin record is unlinked:
       - Repair the identity link.
       - Only reset the password if reset_password=True is explicitly requested for credential recovery.
    4. Preserves the existing PostgreSQL admin UUID, role and active status.
    5. This function never logs or persists the plaintext password.
    """
    normalized_email, _ = _validate_credentials(email, password)
    display_name = (full_name or "").strip() or normalized_email

    # Prevent concurrent command invocations from both observing an empty admin set.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 0x50595156})

    existing_admins = db.scalars(select(User).where(User.role == UserRole.ADMIN_FACULTY)).all()
    if existing_admins:
        if len(existing_admins) > 1 or any(admin.email.lower() != normalized_email for admin in existing_admins):
            raise ProvisioningError(
                "An ADMIN_FACULTY account already exists. Remove or migrate the existing "
                "administrator before provisioning another one."
            )
        same_email_admin = existing_admins[0]
    else:
        same_email_admin = None

    # Check if a non-admin account exists with this email
    existing_user_with_email = db.scalars(select(User).where(User.email == normalized_email)).first()
    if existing_user_with_email is not None and existing_user_with_email.role != UserRole.ADMIN_FACULTY:
        raise ProvisioningError(
            "A user with this email already exists and is not an administrator. "
            "Refusing to promote existing student or non-admin account."
        )

    target_user = same_email_admin or existing_user_with_email

    admin_api = getattr(getattr(client, "auth", None), "admin", None)
    if admin_api is None:
        raise ProvisioningError("Supabase service-role client admin API is unavailable")

    auth_user = _find_auth_user(client, normalized_email)
    metadata = {"full_name": display_name, "role": UserRole.ADMIN_FACULTY.value}

    # Case 1: PostgreSQL record already exists and is correctly linked to the existing Auth identity
    if target_user is not None and auth_user is not None:
        auth_id = _extract_auth_id(auth_user)
        if not auth_id:
            raise ProvisioningError("The existing Supabase identity is missing an ID")
        auth_uuid = uuid.UUID(auth_id)

        current_auth_id = getattr(target_user, "supabase_auth_id", None)
        if current_auth_id is not None and str(current_auth_id) == str(auth_uuid):
            # Already provisioned and correctly linked:
            # Do NOT update password or call update_user_by_id.
            return {
                "status": "already_provisioned",
                "user_id": str(target_user.id),
                "email": target_user.email,
                "role": target_user.role.value if hasattr(target_user.role, "value") else str(target_user.role),
            }

    # Case 2: Supabase Auth identity exists, but target_user is unlinked in PostgreSQL
    if auth_user is not None:
        auth_id = _extract_auth_id(auth_user)
        if not auth_id:
            raise ProvisioningError("The existing Supabase identity is missing an ID")
        auth_uuid = uuid.UUID(auth_id)

        # Only reset credentials if explicitly requested for recovery
        if reset_password:
            try:
                admin_api.update_user_by_id(
                    auth_id,
                    {
                        "password": password,
                        "email_confirm": True,
                        "user_metadata": metadata,
                    },
                )
            except Exception as update_error:
                raise ProvisioningError(
                    f"The existing Supabase identity credentials could not be updated safely: {update_error}"
                ) from update_error

        if target_user is None:
            target_user = User(
                supabase_auth_id=auth_uuid,
                full_name=display_name,
                email=normalized_email,
                email_verified=True,
                role=UserRole.ADMIN_FACULTY,
                account_status=AccountStatus.ACTIVE,
            )
            db.add(target_user)
            status = "created"
        else:
            target_user.supabase_auth_id = auth_uuid
            target_user.full_name = display_name or getattr(target_user, "full_name", None) or normalized_email
            target_user.email_verified = True
            target_user.role = UserRole.ADMIN_FACULTY
            target_user.account_status = AccountStatus.ACTIVE
            status = "updated"

    # Case 3: Supabase Auth identity does NOT exist; create it using the entered password
    else:
        # Safeguard: If the existing admin record already has a non-null supabase_auth_id,
        # but the identity was not found by email in Supabase Auth, refuse to create a duplicate
        # or overwrite the existing link.
        if target_user is not None and getattr(target_user, "supabase_auth_id", None) is not None:
            raise ProvisioningError(
                f"The existing administrator record already has a linked Supabase Auth identity "
                f"({target_user.supabase_auth_id}), but no corresponding user was found in "
                f"Supabase Auth with email '{normalized_email}'. Refusing to create a new Auth "
                f"identity or overwrite the existing link."
            )

        try:
            response = admin_api.create_user({
                "email": normalized_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": metadata,
            })
            created_auth_user = _auth_user_from_response(response)
        except Exception as create_error:
            # Check if user actually existed or was created concurrently
            try:
                created_auth_user = _find_auth_user(client, normalized_email)
            except Exception:
                created_auth_user = None
            if created_auth_user is None:
                raise ProvisioningError(
                    f"Supabase Auth could not create the administrator identity: {create_error}"
                ) from create_error

        auth_id = _extract_auth_id(created_auth_user)
        if not auth_id:
            raise ProvisioningError("Supabase did not return a usable administrator identity")
        auth_uuid = uuid.UUID(auth_id)

        if target_user is None:
            target_user = User(
                supabase_auth_id=auth_uuid,
                full_name=display_name,
                email=normalized_email,
                email_verified=True,
                role=UserRole.ADMIN_FACULTY,
                account_status=AccountStatus.ACTIVE,
            )
            db.add(target_user)
            status = "created"
        else:
            target_user.supabase_auth_id = auth_uuid
            target_user.full_name = display_name or getattr(target_user, "full_name", None) or normalized_email
            target_user.email_verified = True
            target_user.role = UserRole.ADMIN_FACULTY
            target_user.account_status = AccountStatus.ACTIVE
            status = "updated"

    try:
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
        db.refresh(target_user)
    except IntegrityError as exc:
        if hasattr(db, "rollback"):
            db.rollback()
        raise ProvisioningError(
            "Database integrity conflict during administrator provisioning. "
            "A record with this email or Supabase identity may already exist."
        ) from exc

    if target_user.role != UserRole.ADMIN_FACULTY:
        raise ProvisioningError("Administrator role verification failed")
    if target_user.supabase_auth_id != auth_uuid:
        raise ProvisioningError("Administrator identity link verification failed")

    return {
        "status": status,
        "user_id": str(target_user.id),
        "email": target_user.email,
        "role": target_user.role.value if hasattr(target_user.role, "value") else str(target_user.role),
    }


def recover_staging_admin_identity(
    db: Session,
    client: Any,
    *,
    email: str,
    password: str,
    expected_stale_auth_id: str | uuid.UUID,
) -> dict[str, str]:
    """Recover an existing PostgreSQL administrator record pointing to a stale Supabase Auth UUID.

    This function is strictly restricted to the staging environment and requires explicit
    confirmation of the stale Auth UUID being replaced.
    """
    normalized_email, _ = _validate_credentials(email, password)

    try:
        expected_stale_uuid = uuid.UUID(str(expected_stale_auth_id).strip())
    except Exception as exc:
        raise ProvisioningError(
            f"Invalid expected stale Auth UUID format: '{expected_stale_auth_id}'"
        ) from exc

    # 1. Strict staging DATABASE_URL guard (executed before any query, lock or mutation)
    _verify_staging_database(db)

    # 2. Strict staging SUPABASE_URL guard
    _verify_staging_supabase_url(client)

    # Concurrency lock
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 0x50595156})

    # 3. Find existing PostgreSQL ADMIN_FACULTY record
    local_user = db.scalars(select(User).where(User.email == normalized_email)).first()
    if local_user is None:
        raise ProvisioningError(
            f"No database user found with email '{normalized_email}'. Cannot perform identity recovery."
        )
    if local_user.role != UserRole.ADMIN_FACULTY:
        raise ProvisioningError(
            f"User with email '{normalized_email}' has role '{local_user.role}', not ADMIN_FACULTY. "
            f"Refusing to perform recovery on a non-administrator account."
        )

    # 4. Verify current supabase_auth_id matches expected stale UUID
    current_auth_id = getattr(local_user, "supabase_auth_id", None)
    if current_auth_id is None:
        raise ProvisioningError(
            f"The existing administrator record has no linked Supabase Auth identity "
            f"(supabase_auth_id is NULL). Use standard provisioning instead of recovery."
        )
    if str(current_auth_id).lower() != str(expected_stale_uuid).lower():
        raise ProvisioningError(
            f"PostgreSQL administrator record's current supabase_auth_id ({current_auth_id}) "
            f"does not match the expected stale UUID ({expected_stale_uuid}). Refusing recovery."
        )

    admin_api = getattr(getattr(client, "auth", None), "admin", None)
    if admin_api is None:
        raise ProvisioningError("Supabase service-role client admin API is unavailable")

    # 5. Confirm the existing stale Auth UUID cannot be found in staging Auth
    existing_stale_in_staging = _find_auth_user_by_id(client, str(expected_stale_uuid))
    if existing_stale_in_staging is not None:
        raise ProvisioningError(
            f"Expected stale Auth UUID ({expected_stale_uuid}) was unexpectedly found in staging "
            f"Supabase Auth. Refusing recovery to prevent conflicting identity state."
        )

    # 6. Preflight check: confirm no Auth user already exists with the administrator email
    existing_email_auth_user = _find_auth_user(client, normalized_email)
    if existing_email_auth_user is not None:
        existing_email_auth_id = _extract_auth_id(existing_email_auth_user)
        raise ProvisioningError(
            f"An identity with email '{normalized_email}' already exists in staging Supabase Auth "
            f"(ID: {existing_email_auth_id}). If this identity was created in a previous interrupted "
            f"recovery run, manual reconciliation is required to link Auth ID '{existing_email_auth_id}' "
            f"to PostgreSQL user '{local_user.id}'."
        )

    # Phase A: Create new confirmed Supabase Auth identity
    display_name = getattr(local_user, "full_name", None) or normalized_email
    metadata = {"full_name": display_name, "role": UserRole.ADMIN_FACULTY.value}

    try:
        response = admin_api.create_user({
            "email": normalized_email,
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata,
        })
        new_auth_user = _auth_user_from_response(response)
    except Exception as create_error:
        raise ProvisioningError(
            f"Failed to create new Supabase Auth identity during recovery: {type(create_error).__name__}"
        ) from create_error

    new_auth_id = _extract_auth_id(new_auth_user)
    if not new_auth_id:
        raise ProvisioningError("Supabase did not return a usable administrator identity during recovery")
    new_auth_uuid = uuid.UUID(new_auth_id)

    # Phase B: Database transaction commit
    # Preserve exactly: id, email, full_name, role, account_status, email_verified.
    # Update only users.supabase_auth_id.
    try:
        local_user.supabase_auth_id = new_auth_uuid
        db.flush()

        record = db.scalars(
            select(AdministratorBootstrapRecord).where(
                AdministratorBootstrapRecord.email == normalized_email
            )
        ).first()
        if record is not None:
            record.supabase_auth_id = new_auth_uuid
            record.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.flush()

        db.commit()
    except Exception as db_exc:
        if hasattr(db, "rollback"):
            db.rollback()
        raise ProvisioningError(
            f"Supabase Auth identity was successfully created with ID '{new_auth_id}', "
            f"but the database transaction commit failed. The database transaction was rolled back. "
            f"Manual reconciliation is required to link Auth ID '{new_auth_id}' "
            f"to PostgreSQL administrator user '{local_user.id}'."
        ) from db_exc

    # Phase C: Post-commit refresh and verification
    try:
        db.refresh(local_user)
        if local_user.role != UserRole.ADMIN_FACULTY:
            raise ProvisioningError("Administrator role verification failed after recovery")
        if local_user.supabase_auth_id != new_auth_uuid:
            raise ProvisioningError("Administrator identity link verification failed after recovery")
    except Exception as verify_exc:
        raise ProvisioningError(
            f"Database commit succeeded and linked Auth ID '{new_auth_id}' to administrator "
            f"user '{local_user.id}', but post-commit verification failed: {type(verify_exc).__name__}. "
            f"Do not rerun recovery; inspect database state manually."
        ) from verify_exc

    return {
        "status": "recovered",
        "user_id": str(local_user.id),
        "email": local_user.email,
        "role": local_user.role.value if hasattr(local_user.role, "value") else str(local_user.role),
        "previous_auth_id": str(expected_stale_uuid),
        "new_auth_id": str(new_auth_uuid),
    }


def reset_staging_user_password(
    db: Session,
    client: Any,
    *,
    email: str,
    password: str,
    expected_auth_id: str | uuid.UUID,
    confirm_email: bool | None = None,
    allowed_roles: tuple[UserRole, ...] = (UserRole.ADMIN_FACULTY, UserRole.STUDENT),
) -> dict[str, str]:
    """Reset the password for an existing staging user (STUDENT or ADMIN_FACULTY) Auth identity.

    Strictly verifies staging destination and guards, checks the existing PostgreSQL
    record and staging Auth identity match the target email and UUID, and updates
    only the password on that exact existing Auth identity via update_user_by_id().
    Zero PostgreSQL records, roles, or student accounts are modified.
    """
    raw_email = str(email).strip().lower()
    try:
        if raw_email.endswith("@rvce.edu.in"):
            normalized_email = validate_student_email(raw_email)
        else:
            normalized_email = normalize_admin_email(raw_email)
    except HTTPException as exc:
        raise ProvisioningError(str(exc.detail)) from exc
    try:
        validate_password_strength(password)
    except HTTPException as exc:
        raise ProvisioningError(str(exc.detail)) from exc

    try:
        target_uuid = uuid.UUID(str(expected_auth_id).strip())
    except Exception as exc:
        raise ProvisioningError(
            f"Invalid expected Auth UUID format: '{expected_auth_id}'"
        ) from exc

    # 1. Strict staging DATABASE_URL guard
    _verify_staging_database(db)

    # 2. Strict staging SUPABASE_URL guard
    _verify_staging_supabase_url(client)

    # 3. Verify PostgreSQL record exists and is linked to the target UUID
    local_user = db.scalars(select(User).where(User.email == normalized_email)).first()
    if local_user is None:
        raise ProvisioningError(
            f"No database user found with email '{normalized_email}'."
        )
    if local_user.role not in allowed_roles:
        raise ProvisioningError(
            f"User with email '{normalized_email}' has unsupported role '{local_user.role}'. "
            f"Allowed roles: {[r.value for r in allowed_roles]}."
        )
    current_auth_id = getattr(local_user, "supabase_auth_id", None)
    role_desc = "administrator" if local_user.role == UserRole.ADMIN_FACULTY else "student"
    if current_auth_id is None or str(current_auth_id).lower() != str(target_uuid).lower():
        raise ProvisioningError(
            f"PostgreSQL {role_desc} record's supabase_auth_id ({current_auth_id}) "
            f"does not match expected UUID ({target_uuid})."
        )

    admin_api = getattr(getattr(client, "auth", None), "admin", None)
    if admin_api is None or not hasattr(admin_api, "update_user_by_id"):
        raise ProvisioningError("Supabase service-role client admin API is unavailable")

    # 4. Fetch the existing Auth user by the exact UUID
    auth_user = _find_auth_user_by_id(client, str(target_uuid))
    if auth_user is None:
        raise ProvisioningError(
            f"Staging Supabase Auth user with ID '{target_uuid}' not found."
        )

    # 5. Verify Auth user email matches the target user
    auth_email = str(
        getattr(auth_user, "email", None) or (auth_user.get("email") if isinstance(auth_user, dict) else "")
    ).lower().strip()
    if auth_email != normalized_email:
        raise ProvisioningError(
            f"Auth user email '{auth_email}' does not match expected {role_desc} email '{normalized_email}'."
        )

    # 6. Call update_user_by_id on that exact UUID with only the password field (and email_confirm if requested/unconfirmed)
    update_attributes: dict[str, Any] = {"password": password}
    should_confirm = confirm_email if confirm_email is not None else not getattr(local_user, "email_verified", True)
    if should_confirm:
        update_attributes["email_confirm"] = True

    try:
        admin_api.update_user_by_id(
            str(target_uuid),
            update_attributes,
        )
    except Exception as exc:
        raise ProvisioningError(
            f"Failed to update password for Supabase Auth identity '{target_uuid}': {type(exc).__name__}"
        ) from exc

    # 7. Post-update verification: verify the same Auth user still exists and its email remains correct
    verified_auth_user = _find_auth_user_by_id(client, str(target_uuid))
    if verified_auth_user is None:
        raise ProvisioningError(
            "Post-reset verification failed: Auth user could not be found after password update."
        )
    verified_email = str(
        getattr(verified_auth_user, "email", None)
        or (verified_auth_user.get("email") if isinstance(verified_auth_user, dict) else "")
    ).lower().strip()
    if verified_email != normalized_email:
        raise ProvisioningError(
            f"Post-reset verification failed: Auth email changed unexpectedly from '{normalized_email}' to '{verified_email}'."
        )

    # 8. Immediate password authentication test (Instruction 9 & 10)
    auth_service = getattr(client, "auth", None)
    if auth_service is not None and hasattr(auth_service, "sign_in_with_password"):
        try:
            sign_in_resp = auth_service.sign_in_with_password({
                "email": normalized_email,
                "password": password,
            })
            sign_in_user = getattr(sign_in_resp, "user", None) or sign_in_resp
            sign_in_id = _extract_auth_id(sign_in_user).lower()
            sign_in_email = str(
                getattr(sign_in_user, "email", None)
                or (sign_in_user.get("email") if isinstance(sign_in_user, dict) else "")
            ).lower().strip()

            if sign_in_id != str(target_uuid).lower():
                raise ProvisioningError(
                    f"Direct auth test returned mismatched user ID '{sign_in_id}' (expected '{target_uuid}')."
                )
            if sign_in_email != normalized_email:
                raise ProvisioningError(
                    f"Direct auth test returned mismatched email '{sign_in_email}' (expected '{normalized_email}')."
                )

            # Sign out temporary verification session if supported
            if hasattr(auth_service, "sign_out"):
                try:
                    auth_service.sign_out({"scope": "local"})
                except Exception:
                    pass
        except ProvisioningError:
            raise
        except Exception as auth_exc:
            status = getattr(auth_exc, "status", None)
            code = getattr(auth_exc, "code", None)
            err_type = type(auth_exc).__name__
            sanitized_detail = f"status={status}, code={code}, error={err_type}"
            raise ProvisioningError(
                f"Direct password authentication test failed immediately after reset ({sanitized_detail}). "
                "Do not repeat password resets automatically."
            ) from auth_exc

    return {
        "status": "PASSWORD_RESET_AND_AUTH_TEST_SUCCESS",
        "email": normalized_email,
        "auth_id": str(target_uuid),
        "user_id": str(local_user.id),
        "role": local_user.role.value,
    }


def reset_staging_admin_password(
    db: Session,
    client: Any,
    *,
    email: str,
    password: str,
    expected_auth_id: str | uuid.UUID,
    confirm_email: bool | None = None,
    allowed_roles: tuple[UserRole, ...] = (UserRole.ADMIN_FACULTY, UserRole.STUDENT),
) -> dict[str, str]:
    return reset_staging_user_password(
        db,
        client,
        email=email,
        password=password,
        expected_auth_id=expected_auth_id,
        confirm_email=confirm_email,
        allowed_roles=allowed_roles,
    )
