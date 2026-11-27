"""Validation and safe object-path helpers for private academic content."""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException

MAX_FILE_BYTES = 20 * 1024 * 1024

MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_EXTENSIONS = {
    "syllabus": {"pdf", "docx"},
    "pyq": {"pdf"},
    "resource": {"pdf", "docx"},
}

_SAFE_TITLE = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: str | None, *, field: str, max_length: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} is required")
        return None
    normalized = " ".join(_SAFE_TITLE.sub("", str(value)).split())
    if not normalized:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} is required")
        return None
    if len(normalized) > max_length:
        raise HTTPException(status_code=422, detail=f"{field} must be at most {max_length} characters")
    return normalized


def validate_external_url(url: str | None, *, required: bool = False) -> str | None:
    if url is None:
        if required:
            raise HTTPException(status_code=422, detail="Resource URL is required")
        return None
    trimmed = str(url).strip()
    if not trimmed:
        if required:
            raise HTTPException(status_code=422, detail="Resource URL is required")
        return None
    if len(trimmed) > 2000:
        raise HTTPException(status_code=422, detail="Resource URL must be at most 2000 characters")
    parsed = urlparse(trimmed)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(status_code=422, detail="Resource URL must use http or https scheme")
    if not parsed.netloc:
        raise HTTPException(status_code=422, detail="Resource URL must include a valid domain")
    import ipaddress
    host = parsed.netloc.split(":")[0].strip().lower()
    if host in {"localhost", "::1"}:
        raise HTTPException(status_code=422, detail="Resource URL cannot point to internal network hosts")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(status_code=422, detail="Resource URL cannot point to internal network hosts")
    except ValueError:
        pass
    return trimmed


def validate_file(*, category: str, filename: str | None, content_type: str | None, size: int) -> tuple[str, str]:
    if category not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unknown content category")
    if size <= 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds the 20 MB limit")

    original = (filename or "").strip()
    if not original or "." not in original:
        raise HTTPException(status_code=415, detail="A file with a supported extension is required")
    extension = original.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_EXTENSIONS[category]:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS[category]))
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {allowed}")

    expected_mime = MIME_BY_EXTENSION[extension]
    supplied = (content_type or "").split(";", 1)[0].strip().lower()
    accepted = {expected_mime}
    if extension == "docx":
        accepted.add("application/octet-stream")
    if supplied and supplied not in accepted:
        raise HTTPException(status_code=415, detail="The uploaded file type does not match its extension")
    return extension, expected_mime


def safe_object_path(category: str, *, scheme_id, subject_id, extension: str) -> str:
    """Build an object path only from server-generated UUIDs.

    User-provided filenames never become part of the storage path, which
    prevents traversal and overwrite attempts.
    """
    safe_scheme = str(uuid.UUID(str(scheme_id)))
    safe_subject = str(uuid.UUID(str(subject_id)))
    object_id = uuid.uuid4()
    return f"{category}/{safe_scheme}/{safe_subject}/{object_id}.{extension}"


def safe_original_filename(filename: str | None) -> str:
    base = (filename or "document").replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_TITLE.sub("", base).strip() or "document"
    return base[:255]
