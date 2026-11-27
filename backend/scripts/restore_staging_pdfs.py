#!/usr/bin/env python3
"""Restore missing PDF files to staging Supabase Storage.

Strictly staging-only: verifies staging configuration before running.
Does not overwrite existing objects. Preserves all database metadata and IDs.
"""

import hashlib
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.core.config import EXPECTED_STAGING_PROJECT_REF, settings
from app.database.connection import SessionLocal
from app.models.document import UploadedDocument
from app.services.storage import CONTENT_BUCKET, _bucket, ensure_bucket

DOWNLOADS_DIR = Path("/Users/sujalchavan/Downloads")


def main() -> int:
    print("=" * 70)
    print("PYQVERSE STAGING PDF STORAGE RESTORATION")
    print(f"Target Bucket: {CONTENT_BUCKET}")
    print(f"Staging Supabase URL: {settings.SUPABASE_URL}")
    print("=" * 70)

    # 1. Staging safeguard
    if EXPECTED_STAGING_PROJECT_REF not in settings.SUPABASE_URL:
        print(f"ERROR: Destination is not staging ({EXPECTED_STAGING_PROJECT_REF}). Aborting.", file=sys.stderr)
        return 1

    ensure_bucket()
    bucket = _bucket()

    with SessionLocal() as db:
        docs = db.scalars(select(UploadedDocument).order_by(UploadedDocument.uploaded_at)).all()
        print(f"Found {len(docs)} UploadedDocument metadata records in database.\n")

        restored_count = 0
        skipped_count = 0
        failed_count = 0

        for d in docs:
            path = d.storage_path
            parts = path.rsplit("/", 1)
            folder = parts[0] if len(parts) > 1 else ""
            fname = parts[1] if len(parts) > 1 else path

            # Check if object already exists in staging
            already_exists = False
            try:
                files = bucket.list(folder)
                matches = [
                    f for f in files
                    if (f.get("name") if isinstance(f, dict) else getattr(f, "name", None)) == fname
                ]
                if matches:
                    already_exists = True
            except Exception as exc:
                print(f"Warning: Failed to list folder '{folder}': {exc}")

            if already_exists:
                print(f"[ALREADY EXISTS - SKIPPED] Doc ID {d.id}: {path}")
                skipped_count += 1
                continue

            # Find matching original file
            local_file = DOWNLOADS_DIR / d.original_filename
            if not local_file.exists():
                print(f"[ERROR: LOCAL FILE MISSING] Doc ID {d.id}: {d.original_filename}", file=sys.stderr)
                failed_count += 1
                continue

            data = local_file.read_bytes()
            sha256 = hashlib.sha256(data).hexdigest()

            if sha256 != d.content_sha256:
                print(
                    f"[ERROR: CHECKSUM MISMATCH] Doc ID {d.id} ({local_file}): {sha256} vs {d.content_sha256}",
                    file=sys.stderr,
                )
                failed_count += 1
                continue

            # Upload to staging bucket at exact storage_path with retries
            uploaded = False
            for attempt in range(1, 4):
                try:
                    bucket.upload(
                        path,
                        data,
                        {"content-type": "application/pdf", "upsert": "false", "cache-control": "no-store"},
                    )
                    print(f"[RESTORED] Doc ID {d.id} -> {path} ({len(data)} bytes, sha: {sha256[:8]}...)")
                    restored_count += 1
                    uploaded = True
                    break
                except Exception as upload_exc:
                    if attempt < 3:
                        print(f"[RETRY {attempt}/3] Doc ID {d.id}: {upload_exc}. Retrying...")
                    else:
                        print(f"[ERROR: UPLOAD FAILED] Doc ID {d.id}: {upload_exc}", file=sys.stderr)
                        failed_count += 1

        print("\n" + "=" * 70)
        print("RESTORATION SUMMARY")
        print(f"Total documents:   {len(docs)}")
        print(f"Already present:   {skipped_count}")
        print(f"Successfully restored: {restored_count}")
        print(f"Failed / unrecoverable: {failed_count}")
        print("=" * 70)

        return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
