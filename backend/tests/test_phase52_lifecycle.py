import asyncio
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

from app.api import content_routes
from app.api.deps import get_current_user
from app.database.connection import get_db
from app.main import app
from app.models.document import ExamType, PermissionStatus, UploadedDocument
from app.models.resource import LearningResource
from app.models.syllabus import SyllabusDocument, SyllabusVersion, VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.schemas.content import PyqUpdate, ResourceUpdate, SyllabusUpdate
from app.services import storage


class ScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class RowResult:
    def __init__(self, rows):
        self.rows = list(rows)

    def all(self):
        return self.rows


class LookupDB:
    def __init__(self, lookup=None, scalar_values=None, rows=None):
        self.lookup = lookup or {}
        self.scalar_values = list(scalar_values or [])
        self.rows = list(rows or [])
        self.added = []
        self.committed = 0

    def get(self, _model, key):
        return self.lookup.get(key)

    def scalars(self, _query):
        if "uploaded_documents.content_sha256" in str(_query):
            return ScalarResult([])
        if self.scalar_values:
            return ScalarResult(self.scalar_values.pop(0))
        return ScalarResult([])

    def execute(self, query):
        if "pg_advisory_xact_lock" in str(query):
            return RowResult([])
        if "uploaded_documents.content_sha256 IS NULL" in str(query):
            return RowResult(
                [
                    (paper, document)
                    for paper, document in self.rows
                    if document.active and document.content_sha256 is None
                ]
            )
        return RowResult(self.rows)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()

    def commit(self):
        self.committed += 1

    def refresh(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid.uuid4()


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


def _student():
    return SimpleNamespace(id=uuid.uuid4())


def _academic_context():
    subject = SimpleNamespace(
        id=uuid.uuid4(),
        code="CS233AI",
        name="Data Structures",
        subject_type="CORE",
        credits=4,
        description="Core subject",
        semester_id=uuid.uuid4(),
        academic_scheme_id=uuid.uuid4(),
        active=True,
    )
    scheme = SimpleNamespace(id=subject.academic_scheme_id, name="2025 Scheme", code="2025", active=True, college_id=uuid.uuid4())
    semester = SimpleNamespace(id=subject.semester_id, academic_scheme_id=scheme.id, number=3, name="Semester III", active=True)
    return subject, scheme, semester


def _lifecycle_db(subject_id, lookup=None, enroll=True, rows=None):
    profile = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    enrollments = [SimpleNamespace(subject_id=subject_id, active=True)] if enroll else []
    return LookupDB(
        lookup=lookup or {},
        scalar_values=[[profile], enrollments],
        rows=rows or [],
    )


def _pyq(subject_id, *, active=True, status=VerificationStatus.DRAFT):
    document = SimpleNamespace(
        id=uuid.uuid4(),
        storage_path="pyq/path.pdf",
        original_filename="paper.pdf",
        file_type="pdf",
        file_size=100,
        content_sha256="a" * 64,
        title="Question paper",
        description=None,
        active=active,
        verification_status=status,
        permission_status=PermissionStatus.APPROVED if status == VerificationStatus.VERIFIED else PermissionStatus.PENDING,
        uploaded_at=None,
        uploaded_by=uuid.uuid4(),
    )
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=document.id,
        subject_id=subject_id,
        title="Question paper",
        description=None,
        exam_type=ExamType.SEE,
        cie_number=None,
        examination_year=2025,
    )
    return paper, document


def _syllabus(subject_id, *, active=True, status=VerificationStatus.DRAFT):
    document = SimpleNamespace(
        id=uuid.uuid4(),
        syllabus_version_id=uuid.uuid4(),
        storage_path="syllabus/path.pdf",
        original_filename="syllabus.pdf",
        file_type="pdf",
        file_size=100,
        active=active,
        verification_status=status,
        title="Syllabus",
        description=None,
    )
    version = SimpleNamespace(
        id=document.syllabus_version_id,
        subject_id=subject_id,
        active=active,
        verification_status=status,
        version="2025-v1",
        created_at=None,
    )
    return document, version


def _resource(subject_id, *, active=True, status=VerificationStatus.DRAFT):
    return SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject_id,
        storage_path="resource/path.pdf",
        original_filename="notes.pdf",
        file_type="pdf",
        file_size=100,
        active=active,
        verification_status=status,
        title="Notes",
        description=None,
        resource_type="NOTES",
        uploaded_at=None,
        updated_at=None,
        uploaded_by=uuid.uuid4(),
    )


def _capture(monkeypatch):
    calls = []

    def fake(path, expires_in=storage.SIGNED_URL_TTL_SECONDS, **kwargs):
        calls.append({"path": path, "expires_in": expires_in, **kwargs})
        return "https://signed.example/private"

    monkeypatch.setattr(content_routes.storage, "create_signed_url", fake)
    return calls


def test_draft_upload_creates_active_record(monkeypatch):
    subject, scheme, semester = _academic_context()
    db = LookupDB(lookup={subject.id: subject, scheme.id: scheme, semester.id: semester})
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *args, **kwargs: None)

    upload = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test"),
        filename="paper.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    asyncio.run(
        content_routes.admin_upload_pyq(
            file=upload,
            subject_id=subject.id,
            exam_type="SEE",
            examination_year=2025,
            cie_number=None,
            title=None,
            description=None,
            status="DRAFT",
            admin=_admin(),
            db=db,
        )
    )

    document = next(value for value in db.added if isinstance(value, UploadedDocument))
    assert document.active is True
    assert document.verification_status == VerificationStatus.DRAFT
    assert document.permission_status == PermissionStatus.PENDING


def test_publishing_draft_makes_it_visible_to_students(monkeypatch):
    subject_id = uuid.uuid4()
    paper, document = _pyq(subject_id)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    signed = _capture(monkeypatch)

    updated = content_routes.admin_update_pyq(paper.id, PyqUpdate(status="VERIFIED"), _admin(), db)

    assert updated["verification_status"] == "VERIFIED"
    assert document.active is True
    assert document.permission_status == PermissionStatus.APPROVED
    result = content_routes.student_download("pyq", paper.id, _student(), db)
    assert result["url"] == "https://signed.example/private"
    assert signed


def test_archiving_published_record_removes_it_from_students(monkeypatch):
    subject_id = uuid.uuid4()
    paper, document = _pyq(subject_id, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    signed = _capture(monkeypatch)

    content_routes.admin_archive_pyq(paper.id, _admin(), db)
    assert document.active is False

    with pytest.raises(HTTPException) as error:
        content_routes.student_download("pyq", paper.id, _student(), db)
    assert error.value.status_code == 404
    assert signed == []


def test_restoring_published_record_makes_it_visible_again(monkeypatch):
    subject_id = uuid.uuid4()
    paper, document = _pyq(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    signed = _capture(monkeypatch)

    content_routes.admin_update_pyq(paper.id, PyqUpdate(active=True), _admin(), db)
    assert document.active is True
    assert document.verification_status == VerificationStatus.VERIFIED

    assert content_routes.student_download("pyq", paper.id, _student(), db)["url"] == "https://signed.example/private"


def test_publishing_archived_draft_reactivates_all_kinds(monkeypatch):
    subject_id = uuid.uuid4()
    signed = _capture(monkeypatch)

    paper, document = _pyq(subject_id, active=False)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    content_routes.admin_update_pyq(paper.id, PyqUpdate(status="VERIFIED"), _admin(), db)
    assert document.active is True
    assert content_routes.student_download("pyq", paper.id, _student(), db)["disposition"] == "attachment"

    syllabus, version = _syllabus(subject_id, active=False)
    db = _lifecycle_db(subject_id, lookup={syllabus.id: syllabus, version.id: version})
    content_routes.admin_update_syllabus(syllabus.id, SyllabusUpdate(status="VERIFIED"), _admin(), db)
    assert syllabus.active is True
    assert version.active is True
    assert content_routes.student_download("syllabus", syllabus.id, _student(), db)["disposition"] == "attachment"

    resource = _resource(subject_id, active=False)
    db = _lifecycle_db(subject_id, lookup={resource.id: resource})
    content_routes.admin_update_resource(resource.id, ResourceUpdate(status="VERIFIED"), _admin(), db)
    assert resource.active is True
    assert content_routes.student_download("resource", resource.id, _student(), db)["disposition"] == "attachment"


def test_editing_archived_record_preserves_archive_state(monkeypatch):
    subject_id = uuid.uuid4()
    signed = _capture(monkeypatch)

    paper, document = _pyq(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    content_routes.admin_update_pyq(paper.id, PyqUpdate(title="Updated paper"), _admin(), db)
    assert document.active is False
    assert document.verification_status == VerificationStatus.VERIFIED
    assert signed == []

    syllabus, version = _syllabus(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={syllabus.id: syllabus, version.id: version})
    content_routes.admin_update_syllabus(syllabus.id, SyllabusUpdate(title="Updated syllabus"), _admin(), db)
    assert syllabus.active is False
    assert version.active is False

    resource = _resource(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={resource.id: resource})
    content_routes.admin_update_resource(resource.id, ResourceUpdate(title="Updated notes"), _admin(), db)
    assert resource.active is False


def test_explicit_keep_archived_overrides_publish_transition(monkeypatch):
    subject_id = uuid.uuid4()
    paper, document = _pyq(subject_id, active=False, status=VerificationStatus.DRAFT)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    _capture(monkeypatch)

    content_routes.admin_update_pyq(
        paper.id, PyqUpdate(status="VERIFIED", active=False), _admin(), db
    )
    assert document.verification_status == VerificationStatus.VERIFIED
    assert document.active is False

    with pytest.raises(HTTPException) as error:
        content_routes.student_download("pyq", paper.id, _student(), db)
    assert error.value.status_code == 404


def test_archived_content_cannot_be_downloaded_by_students(monkeypatch):
    subject_id = uuid.uuid4()
    signed = _capture(monkeypatch)

    syllabus, version = _syllabus(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={syllabus.id: syllabus, version.id: version})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("syllabus", syllabus.id, _student(), db)
    assert error.value.status_code == 404

    paper, document = _pyq(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("pyq", paper.id, _student(), db)
    assert error.value.status_code == 404

    resource = _resource(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={resource.id: resource})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("resource", resource.id, _student(), db)
    assert error.value.status_code == 404

    assert signed == []


def test_admin_can_list_restore_and_download_archived_content(monkeypatch):
    subject_id = uuid.uuid4()
    subject, _scheme, _semester = _academic_context()
    subject.id = subject_id
    paper, document = _pyq(subject_id, active=False, status=VerificationStatus.VERIFIED)
    db = LookupDB(
        lookup={subject.id: subject, paper.id: paper, document.id: document},
        rows=[(paper, document)],
    )
    signed = _capture(monkeypatch)

    listed = content_routes.admin_list_pyqs(admin=_admin(), db=db)
    assert any(item["id"] == str(paper.id) for item in listed["items"])

    assert content_routes.admin_download("pyq", paper.id, _admin(), db)["url"] == "https://signed.example/private"

    content_routes.admin_update_pyq(paper.id, PyqUpdate(active=True), _admin(), db)
    assert document.active is True
    assert signed


def test_students_cannot_access_admin_lifecycle_endpoints():
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
        content_id = uuid.uuid4()
        cases = [
            ("get", f"/api/v1/admin/pyqs", None),
            ("patch", f"/api/v1/admin/pyqs/{content_id}", {"status": "VERIFIED"}),
            ("delete", f"/api/v1/admin/pyqs/{content_id}", None),
            ("patch", f"/api/v1/admin/syllabus/{content_id}", {"active": True}),
            ("delete", f"/api/v1/admin/syllabus/{content_id}", None),
            ("patch", f"/api/v1/admin/resources/{content_id}", {"active": True}),
            ("delete", f"/api/v1/admin/resources/{content_id}", None),
        ]
        for method, path, body in cases:
            response = client.request(
                method,
                path,
                json=body,
                headers={"Authorization": "Bearer test-token"},
            )
            assert response.status_code == 403, path
    finally:
        app.dependency_overrides.clear()


def test_preview_and_download_continue_after_lifecycle_changes(monkeypatch):
    subject_id = uuid.uuid4()
    paper, document = _pyq(subject_id, status=VerificationStatus.VERIFIED)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    calls = _capture(monkeypatch)

    preview = content_routes.student_download("pyq", paper.id, _student(), db, preview=True)
    db = _lifecycle_db(subject_id, lookup={paper.id: paper, document.id: document})
    download = content_routes.student_download("pyq", paper.id, _student(), db, preview=False)

    assert preview["disposition"] == "inline"
    assert download["disposition"] == "attachment"
    assert download["filename"] == "paper.pdf"
    assert "download_filename" not in calls[-2]
    assert calls[-1]["download_filename"] == "paper.pdf"


def test_student_list_queries_exclude_draft_and_archived_rows():
    subject_id = uuid.uuid4()
    student = _student()

    class StudentDB:
        def __init__(self):
            self.statements = []
            self.scalar_statements = []
            self.calls = 0

        def scalars(self, _query):
            self.scalar_statements.append(str(_query))
            self.calls += 1
            if self.calls == 1:
                return ScalarResult([SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())])
            if self.calls == 2:
                return ScalarResult([SimpleNamespace(subject_id=subject_id, active=True)])
            return ScalarResult([])

        def execute(self, query):
            self.statements.append(str(query))
            return RowResult([])

    db = StudentDB()
    content_routes.student_list_pyqs(student=student, db=db)
    assert "uploaded_documents.active" in db.statements[-1]
    assert "uploaded_documents.verification_status" in db.statements[-1]
    assert "uploaded_documents.permission_status" in db.statements[-1]

    db = StudentDB()
    content_routes.student_list_syllabus(student=student, db=db)
    assert "syllabus_documents.active" in db.statements[-1]
    assert "syllabus_documents.verification_status" in db.statements[-1]

    db = StudentDB()
    content_routes.student_list_resources(student=student, db=db)
    assert "learning_resources.active" in db.scalar_statements[-1]
    assert "learning_resources.verification_status" in db.scalar_statements[-1]
