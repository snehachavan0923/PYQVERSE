#!/usr/bin/env python3
"""Provision the single initial ADMIN_FACULTY account.

Usage:
    python scripts/provision_admin.py

Credentials may be supplied through ADMIN_EMAIL, ADMIN_FULL_NAME and
ADMIN_PASSWORD environment variables. Missing values are requested with a
secure interactive prompt. The password is never printed or stored in plaintext.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core.security import create_supabase_service_client
from app.database.connection import SessionLocal
from app.services.admin_provisioning import (
    ProvisioningError,
    provision_admin,
    recover_staging_admin_identity,
    reset_staging_admin_password,
    reset_staging_user_password,
)


def _read_value(label: str, env_name: str, cli_value: str | None) -> str:
    value = cli_value or os.getenv(env_name) or ""
    if value:
        return value.strip()
    return input(f"{label}: ").strip()


def _read_password(label: str = "Administrator password", confirm_label: str = "Confirm administrator password") -> str:
    password = os.getenv("ADMIN_PASSWORD") or os.getenv("PYQVERSE_PASSWORD")
    if password:
        return password
    password = getpass.getpass(f"{label}: ")
    confirmation = getpass.getpass(f"{confirm_label}: ")
    if password != confirmation:
        raise ProvisioningError("Passwords do not match")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the PYQVERSE administrator account.")
    parser.add_argument("--email", help="Account email address")
    parser.add_argument("--name", help="Administrator full name")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Explicitly reset credentials if an unlinked Supabase identity already exists",
    )
    parser.add_argument(
        "--recover-stale-auth-link",
        action="store_true",
        help="Explicitly recover a staging administrator identity whose PostgreSQL record points to a stale Auth UUID",
    )
    parser.add_argument(
        "--expected-stale-auth-id",
        help="The expected stale Supabase Auth UUID to replace during staging recovery",
    )
    parser.add_argument(
        "--reset-staging-admin-password",
        action="store_true",
        help="Securely reset the password of the existing staging administrator or student Auth identity",
    )
    parser.add_argument(
        "--reset-staging-password",
        action="store_true",
        help="Securely reset the password of an existing staging user (STUDENT or ADMIN_FACULTY)",
    )
    parser.add_argument(
        "--auth-id",
        help="The expected Supabase Auth UUID of the existing staging user",
    )
    parser.add_argument(
        "--confirm-email",
        action="store_true",
        help="Also confirm the email in Supabase Auth if currently unconfirmed",
    )
    args = parser.parse_args()

    try:
        is_reset = args.reset_staging_admin_password or args.reset_staging_password
        email_prompt = "Account email" if is_reset else "Administrator email"
        email = _read_value(email_prompt, "ADMIN_EMAIL", args.email)
        if args.recover_stale_auth_link or is_reset:
            full_name = args.name or os.getenv("ADMIN_FULL_NAME") or ""
        else:
            full_name = _read_value("Administrator full name", "ADMIN_FULL_NAME", args.name)
        pw_label = "New password" if is_reset else "Administrator password"
        pw_confirm_label = "Confirm new password" if is_reset else "Confirm administrator password"
        password = _read_password(pw_label, pw_confirm_label)
        client = create_supabase_service_client()

        with SessionLocal() as db:
            if is_reset:
                auth_id = _read_value(
                    "Supabase Auth UUID",
                    "ADMIN_AUTH_ID",
                    args.auth_id or args.expected_stale_auth_id,
                )
                result = reset_staging_user_password(
                    db,
                    client,
                    email=email,
                    password=password,
                    expected_auth_id=auth_id,
                    confirm_email=True if args.confirm_email else None,
                )
                # Also verify anon client authentication against staging
                try:
                    from app.core.security import create_supabase_anon_client
                    anon_client = create_supabase_anon_client()
                    anon_resp = anon_client.auth.sign_in_with_password({
                        "email": email,
                        "password": password,
                    })
                    if hasattr(anon_client.auth, "sign_out"):
                        try:
                            anon_client.auth.sign_out({"scope": "local"})
                        except Exception:
                            pass
                    print("Direct anon-client authentication test: SUCCESS")
                except Exception as anon_exc:
                    status = getattr(anon_exc, "status", None)
                    code = getattr(anon_exc, "code", None)
                    err_type = type(anon_exc).__name__
                    raise ProvisioningError(
                        f"Direct anon-client authentication test failed (status={status}, code={code}, error={err_type})."
                    ) from anon_exc
            elif args.recover_stale_auth_link:
                stale_auth_id = _read_value(
                    "Expected stale Supabase Auth UUID",
                    "EXPECTED_STALE_AUTH_ID",
                    args.expected_stale_auth_id,
                )
                result = recover_staging_admin_identity(
                    db,
                    client,
                    email=email,
                    password=password,
                    expected_stale_auth_id=stale_auth_id,
                )
            else:
                reset_password = args.reset_password or (
                    os.getenv("ADMIN_RESET_PASSWORD", "").lower() in ("true", "1", "yes")
                )
                result = provision_admin(
                    db,
                    client,
                    email=email,
                    full_name=full_name,
                    password=password,
                    reset_password=reset_password,
                )
    except ProvisioningError as exc:
        print(f"Provisioning failed: {exc}", file=sys.stderr)
        return 1
    except HTTPException as exc:
        print(f"Provisioning failed: {exc.detail}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Provisioning cancelled.", file=sys.stderr)
        return 130

    if result.get("status") == "PASSWORD_RESET_AND_AUTH_TEST_SUCCESS":
        print("PASSWORD_RESET_AND_AUTH_TEST_SUCCESS")
        print(f"Email: {result['email']}")
        print(f"Supabase Auth ID: {result['auth_id']}")
        return 0

    print("Administrator provisioning/recovery/reset complete.")
    print(f"Email: {result['email']}")
    if "role" in result:
        print(f"Role: {result['role']}")
    print(f"Status: {result['status']}")
    if "new_auth_id" in result:
        print(f"New Supabase Auth ID: {result['new_auth_id']}")
    elif "auth_id" in result:
        print(f"Supabase Auth ID: {result['auth_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
