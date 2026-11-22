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
from app.services.admin_provisioning import ProvisioningError, provision_admin


def _read_value(label: str, env_name: str, cli_value: str | None) -> str:
    value = cli_value or os.getenv(env_name) or ""
    if value:
        return value.strip()
    return input(f"{label}: ").strip()


def _read_password() -> str:
    password = os.getenv("ADMIN_PASSWORD")
    if password:
        return password
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        raise ProvisioningError("Passwords do not match")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision the PYQVERSE administrator account.")
    parser.add_argument("--email", help="Administrator email address")
    parser.add_argument("--name", help="Administrator full name")
    args = parser.parse_args()

    try:
        email = _read_value("Administrator email", "ADMIN_EMAIL", args.email)
        full_name = _read_value("Administrator full name", "ADMIN_FULL_NAME", args.name)
        password = _read_password()
        client = create_supabase_service_client()
        with SessionLocal() as db:
            result = provision_admin(
                db,
                client,
                email=email,
                full_name=full_name,
                password=password,
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

    print("Administrator provisioning complete.")
    print(f"Email: {result['email']}")
    print(f"Role: {result['role']}")
    print(f"Status: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
