import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import content_routes
from app.api.deps import get_current_user
from app.database.connection import get_db
from app.main import app
from app.models.document import PermissionStatus
from app.models.syllabus import VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.services import storage


class ScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class LookupDB:
    def __init__(self, lookup=None, scalar_values=None):
        self.lookup = lookup or {}
        self.scalar_values = list(scalar_values or [])

    def get(self, _model, key):
        return self.lookup.get(key)

    def scalars(self, _query):
        if self.scalar_values:
            return ScalarResult(self.scalar_values.pop(0))
        return ScalarResult([])


def _student():
    return SimpleNamespace(id=uuid.uuid4())


def _admin():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin",
        email="admin@example.com",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        last_login_at=None,
    )


def _download_db(subject_id, enroll=True, lookup=None):
    profile = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    enrollments = [SimpleNamespace(subject_id=subject_id, active=True)] if enroll else []
    return LookupDB(lookup=lookup, scalar_values=[[profile], enrollments])


def _syllabus_document(subject_id, *, file_type="pdf", active=True, status=VerificationStatus.VERIFIED):
    document = SimpleNamespace(
        id=uuid.uuid4(),
        syllabus_version_id=uuid.uuid4(),
        storage_path="syllabus/path.pdf",
        original_filename="syllabus.pdf",
        file_type=file_type,
        active=active,
        verification_status=status,
    )
    version = SimpleNamespace(
        id=document.syllabus_version_id,
        subject_id=subject_id,
        active=active,
        verification_status=status,
    )
    return document, version


def _pyq(subject_id, *, file_type="pdf", active=True, status=VerificationStatus.VERIFIED):
    document = SimpleNamespace(
        id=uuid.uuid4(),
        storage_path="pyq/path.pdf",
        original_filename="paper.pdf",
        file_type=file_type,
        active=active,
        verification_status=status,
        permission_status=PermissionStatus.APPROVED,
    )
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=document.id,
        subject_id=subject_id,
    )
    return paper, document


def _resource(subject_id, *, file_type="pdf", active=True, status=VerificationStatus.VERIFIED):
    return SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject_id,
        storage_path="resource/path.pdf",
        original_filename="resource.pdf",
        file_type=file_type,
        active=active,
        verification_status=status,
    )


def _capture_signed_urls(monkeypatch):
    calls = []

    def fake(path, expires_in=storage.SIGNED_URL_TTL_SECONDS, **kwargs):
        calls.append({"path": path, "expires_in": expires_in, **kwargs})
        return "https://signed.example/private"

    monkeypatch.setattr(content_routes.storage, "create_signed_url", fake)
    return calls


def test_student_syllabus_preview_is_inline_and_authorized(monkeypatch):
    subject_id = uuid.uuid4()
    document, version = _syllabus_document(subject_id)
    db = _download_db(subject_id, lookup={document.id: document, version.id: version})
    calls = _capture_signed_urls(monkeypatch)

    result = content_routes.student_download(
        "syllabus", document.id, _student(), db, preview=True
    )

    assert result["url"] == "https://signed.example/private"
    assert result["disposition"] == "inline"
    assert result["filename"] == "syllabus.pdf"
    assert result["expires_in"] == storage.SIGNED_URL_TTL_SECONDS
    assert calls[-1].get("download_filename") is None


def test_student_pyq_and_resource_preview_are_inline(monkeypatch):
    subject_id = uuid.uuid4()
    paper, paper_document = _pyq(subject_id)
    db = _download_db(subject_id, lookup={paper.id: paper, paper_document.id: paper_document})
    calls = _capture_signed_urls(monkeypatch)

    result = content_routes.student_download("pyq", paper.id, _student(), db, preview=True)
    assert result["disposition"] == "inline"
    assert calls[-1].get("download_filename") is None

    resource = _resource(subject_id)
    db = _download_db(subject_id, lookup={resource.id: resource})
    result = content_routes.student_download("resource", resource.id, _student(), db, preview=True)
    assert result["disposition"] == "inline"
    assert calls[-1].get("download_filename") is None


def test_student_preview_rejects_draft_archived_and_unauthorized_content(monkeypatch):
    subject_id = uuid.uuid4()
    calls = _capture_signed_urls(monkeypatch)

    draft_document, draft_version = _syllabus_document(
        subject_id, status=VerificationStatus.DRAFT
    )
    db = _download_db(
        subject_id, lookup={draft_document.id: draft_document, draft_version.id: draft_version}
    )
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("syllabus", draft_document.id, _student(), db, preview=True)
    assert error.value.status_code == 404

    archived_document, archived_version = _syllabus_document(subject_id, active=False)
    db = _download_db(
        subject_id,
        lookup={
            archived_document.id: archived_document,
            archived_version.id: archived_version,
        },
    )
    with pytest.raises(HTTPException) as error:
        content_routes.student_download(
            "syllabus", archived_document.id, _student(), db, preview=True
        )
    assert error.value.status_code == 404

    unauthorized_resource = _resource(uuid.uuid4())
    db = _download_db(subject_id, enroll=False, lookup={unauthorized_resource.id: unauthorized_resource})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download(
            "resource", unauthorized_resource.id, _student(), db, preview=True
        )
    assert error.value.status_code == 403
    assert calls == []


def test_student_preview_rejects_non_pdf_documents(monkeypatch):
    subject_id = uuid.uuid4()
    document, version = _syllabus_document(subject_id, file_type="docx")
    db = _download_db(subject_id, lookup={document.id: document, version.id: version})
    calls = _capture_signed_urls(monkeypatch)

    with pytest.raises(HTTPException) as error:
        content_routes.student_download("syllabus", document.id, _student(), db, preview=True)
    assert error.value.status_code == 415
    assert calls == []


def test_download_mode_forces_attachment_with_original_filename(monkeypatch):
    subject_id = uuid.uuid4()
    document, version = _syllabus_document(subject_id)
    db = _download_db(subject_id, lookup={document.id: document, version.id: version})
    calls = _capture_signed_urls(monkeypatch)

    result = content_routes.student_download(
        "syllabus", document.id, _student(), db, preview=False
    )

    assert result["disposition"] == "attachment"
    assert result["filename"] == "syllabus.pdf"
    assert calls[-1]["download_filename"] == "syllabus.pdf"


def test_admin_preview_requires_admin_role(monkeypatch):
    student = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    app.dependency_overrides[get_current_user] = lambda: student

    def fake_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = fake_db
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/admin/pyq/{uuid.uuid4()}/download?preview=true",
            headers={"Authorization": "Bearer test-token"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_preview_for_each_kind_is_inline(monkeypatch):
    subject_id = uuid.uuid4()
    calls = _capture_signed_urls(monkeypatch)

    document, _version = _syllabus_document(subject_id)
    db = LookupDB(lookup={document.id: document})
    result = content_routes.admin_download("syllabus", document.id, _admin(), db, preview=True)
    assert result["disposition"] == "inline"
    assert calls[-1].get("download_filename") is None

    paper, paper_document = _pyq(subject_id)
    db = LookupDB(lookup={paper.id: paper, paper_document.id: paper_document})
    result = content_routes.admin_download("pyq", paper.id, _admin(), db, preview=True)
    assert result["disposition"] == "inline"

    resource = _resource(subject_id)
    db = LookupDB(lookup={resource.id: resource})
    result = content_routes.admin_download("resource", resource.id, _admin(), db, preview=True)
    assert result["disposition"] == "inline"


def test_admin_download_forces_attachment(monkeypatch):
    subject_id = uuid.uuid4()
    paper, paper_document = _pyq(subject_id)
    db = LookupDB(lookup={paper.id: paper, paper_document.id: paper_document})
    calls = _capture_signed_urls(monkeypatch)

    result = content_routes.admin_download("pyq", paper.id, _admin(), db, preview=False)

    assert result["disposition"] == "attachment"
    assert calls[-1]["download_filename"] == "paper.pdf"


def test_storage_signed_url_requests_attachment_option(monkeypatch):
    captured = {}

    class Bucket:
        def create_signed_url(self, path, expires_in, options=None):
            captured["path"] = path
            captured["expires_in"] = expires_in
            captured["options"] = options
            return {"signedURL": "https://signed.example/file"}

    monkeypatch.setattr(storage, "_bucket", lambda: Bucket())
    url = storage.create_signed_url("syllabus/path.pdf", download_filename="syllabus.pdf")

    assert url == "https://signed.example/file"
    assert captured["options"] == {"download": "syllabus.pdf"}

    captured.clear()
    storage.create_signed_url("syllabus/path.pdf")
    assert captured["options"] is None
