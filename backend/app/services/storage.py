import os
import re
import uuid
from pathlib import PurePosixPath

from fastapi import HTTPException, UploadFile

from app.core.security import create_supabase_service_client


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "pyqverse-private")


def validate_upload(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", PurePosixPath(file.filename).name)
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 20 MB upload limit")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    return content


def object_name(category: str, original_filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", PurePosixPath(original_filename).name)
    category = re.sub(r"[^A-Za-z0-9_-]", "_", category)
    return f"{category}/{uuid.uuid4().hex}/{safe_name}"


def upload_private_object(category: str, file: UploadFile) -> tuple[str, bytes, str]:
    content = validate_upload(file)
    path = object_name(category, file.filename or "document")
    client = create_supabase_service_client()
    try:
        client.storage.from_(BUCKET).upload(
            path,
            content,
            file_options={"content-type": file.content_type or "application/octet-stream", "upsert": "false"},
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="File storage is unavailable") from exc
    return path, content, file.content_type or "application/octet-stream"


def create_signed_download(path: str, expires_seconds: int = 300) -> str:
    client = create_supabase_service_client()
    try:
        response = client.storage.from_(BUCKET).create_signed_url(path, expires_seconds)
        return response["signedURL"] if isinstance(response, dict) else getattr(response, "signedURL")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Unable to create a secure download link") from exc
