"""Private Supabase Storage helpers.

All content buckets are private. Files are only reachable through short-lived
signed URLs produced by authenticated backend endpoints; the service-role key
never leaves the backend.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import HTTPException

from app.core.security import create_supabase_service_client

logger = logging.getLogger(__name__)

CONTENT_BUCKET = "pyqverse-content"
SIGNED_URL_TTL_SECONDS = 300
MAX_FILE_BYTES = 20 * 1024 * 1024


class StorageError(Exception):
    """Raised when a private storage operation cannot be completed."""


def _bucket():
    client = create_supabase_service_client()
    try:
        return client.storage.from_(CONTENT_BUCKET)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise StorageError("Private storage is unavailable") from exc


def ensure_bucket() -> None:
    """Create the private content bucket if it does not exist yet."""
    client = create_supabase_service_client()
    try:
        buckets = client.storage.list_buckets()
        names = set()
        for bucket in buckets or []:
            name = getattr(bucket, "name", None) or (
                bucket.get("name") if isinstance(bucket, dict) else None
            )
            if name:
                names.add(name)
        if CONTENT_BUCKET not in names:
            try:
                client.storage.create_bucket(CONTENT_BUCKET, options={"public": False})
            except Exception:
                # A concurrent request may have created it already.
                logger.info("Storage bucket creation raced or was already completed")
    except HTTPException:
        raise
    except Exception as exc:
        raise StorageError("Private storage is unavailable") from exc


def upload_bytes(path: str, data: bytes, content_type: str) -> None:
    ensure_bucket()
    bucket = _bucket()
    try:
        bucket.upload(
            path,
            data,
            {"content-type": content_type, "upsert": "false", "cache-control": "no-store"},
        )
    except Exception as exc:
        raise StorageError("The file could not be uploaded to private storage") from exc


def download_bytes(path: str) -> bytes:
    bucket = _bucket()
    try:
        return bucket.download(path)
    except Exception as exc:
        raise StorageError("The stored file could not be verified") from exc


def delete_object(path: str) -> None:
    if not path:
        return
    bucket = _bucket()
    try:
        bucket.remove([path])
    except Exception as exc:
        raise StorageError("The stored file could not be removed") from exc


def create_signed_url(
    path: str,
    expires_in: int = SIGNED_URL_TTL_SECONDS,
    *,
    download_filename: str | None = None,
) -> str:
    """Create a short-lived signed URL for a private object.

    Without ``download_filename`` the URL serves the object inline (used by the
    browser PDF viewer for previews). Passing a filename forces an attachment
    response so the browser downloads the file while preserving its name.
    """
    bucket = _bucket()
    options = {"download": download_filename} if download_filename else None
    try:
        if options is None:
            result = bucket.create_signed_url(path, expires_in)
        else:
            result = bucket.create_signed_url(path, expires_in, options=options)
    except Exception as exc:
        raise StorageError("A secure download link could not be created") from exc
    if isinstance(result, dict):
        url = result.get("signedURL") or result.get("signedUrl") or result.get("signed_url")
    else:
        url = getattr(result, "signed_url", None) or getattr(result, "signedURL", None)
    if not url:
        raise StorageError("A secure download link could not be created")
    return str(url)


def storage_timestamp() -> datetime:
    return datetime.utcnow()
