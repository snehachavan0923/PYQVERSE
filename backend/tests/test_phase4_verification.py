import asyncio
import io
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.api import auth_routes, content_routes
from app.api.deps import get_current_user
from app.database.connection import get_db
from app.main import app
from app.models.academic import AcademicScheme, Semester, Subject
from app.models.document import ExamType, PermissionStatus, QuestionPaper, UploadedDocument
from app.models.resource import LearningResource, ResourceType
from app.models.syllabus import SyllabusDocument, SyllabusVersion, VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.schemas.academic import SemesterResponse, SubjectResponse
from app.schemas.admin import AdminProfileUpdateRequest
from app.schemas.content import PyqUpdate, ResourceUpdate, SyllabusUpdate
from app.services import storage


class ScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values

    def unique(self):
        return self

    def first(self):
        return self.values[0] if self.values else None


class RowResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values


class ScalarDB:
    def __init__(self, values):
        self.values = list(values)

    def scalars(self, _query):
        return ScalarResult(self.values)


class ExecuteDB:
    def __init__(self, rows):
        self.rows = list(rows)

    def execute(self, _query):
        return RowResult(self.rows)


class LookupDB:
    def __init__(self, lookup=None, scalar_values=None):
        self.lookup = lookup or {}
        self.scalar_values = list(scalar_values or [])
        self.added = []
        self.committed = 0

    def get(self, _model, key):
        return self.lookup.get(key)

    def scalars(self, _query):
        if self.scalar_values:
            return ScalarResult(self.scalar_values.pop(0))
        return ScalarResult([])

    def execute(self, query):
        if "pg_advisory_xact_lock" in str(query):
            return None
        return RowResult([])

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()

    def commit(self):
        self.committed += 1

    def rollback(self):
        return None

    def refresh(self, value):
        if getattr(value, "id", None) is None:
            value.id = uuid.uuid4()


def _subject():
    return SimpleNamespace(
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


def _scheme():
    return SimpleNamespace(id=uuid.uuid4(), name="2025 Scheme", code="2025", active=True, college_id=uuid.uuid4())


def _semester(scheme_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        academic_scheme_id=scheme_id,
        number=3,
        name="Semester III",
        active=True,
    )


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


def test_public_academic_response_contract_supports_onboarding_and_profile():
    assert "academic_scheme_id" in SemesterResponse.model_fields
    assert {"semester_id", "academic_scheme_id", "credits", "description"} <= set(
        SubjectResponse.model_fields
    )


def test_admin_academic_list_payloads_include_frontend_fields(monkeypatch):
    admin = _admin()
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (admin, None))
    scheme = _scheme()
    semester = _semester(scheme.id)
    subject = _subject()
    subject.academic_scheme_id = scheme.id
    subject.semester_id = semester.id
    basket = SimpleNamespace(
        id=uuid.uuid4(),
        name="Open Elective",
        academic_scheme_id=scheme.id,
        semester_id=semester.id,
        active=True,
    )
    option = SimpleNamespace(subject_id=subject.id)

    semesters = auth_routes.admin_semesters("token", ScalarDB([semester]))
    subjects = auth_routes.admin_subjects("token", ScalarDB([subject]))
    electives = auth_routes.admin_elective_options("token", ExecuteDB([(basket, option, subject)]))

    assert semesters[0]["academic_scheme_id"] == str(scheme.id)
    assert subjects[0]["description"] == "Core subject"
    assert subjects[0]["academic_scheme_id"] == str(scheme.id)
    assert electives[0]["academic_scheme_id"] == str(scheme.id)
    assert electives[0]["semester_id"] == str(semester.id)


def test_admin_profile_update_persists_and_is_returned_again(monkeypatch):
    admin = _admin()
    admin.full_name = "Old Name"
    db = LookupDB()
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda database, token: (admin, None))

    updated = auth_routes.update_admin_profile(
        AdminProfileUpdateRequest(full_name="  New   Name  "), "token", db
    )
    assert admin.full_name == "New Name"
    assert updated["full_name"] == "New Name"
    assert db.committed == 1

    reloaded = auth_routes.admin_profile("token", db)
    assert reloaded["full_name"] == "New Name"
    assert reloaded["email"] == admin.email


def test_admin_user_filters_are_applied_to_query(monkeypatch):
    admin = _admin()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student One",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        last_login_at=None,
    )
    branch_id = uuid.uuid4()
    semester_id = uuid.uuid4()
    profile = SimpleNamespace(
        user_id=user.id,
        usn="1RV22CS001",
        profile_completed=True,
        branch_id=branch_id,
        current_semester_id=semester_id,
    )

    class FilterDB:
        def __init__(self):
            self.queries = []
            self.scalars_calls = 0

        def scalar(self, query):
            self.queries.append(query)
            return 1

        def scalars(self, query):
            self.queries.append(query)
            self.scalars_calls += 1
            if self.scalars_calls == 1:
                return ScalarResult([user])
            if self.scalars_calls == 2:
                return ScalarResult([profile])
            return ScalarResult([])

    db = FilterDB()
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda database, token: (admin, None))
    result = auth_routes.admin_users(
        "token",
        db,
        page=2,
        page_size=10,
        role="STUDENT",
        status="ACTIVE",
        branch_id=branch_id,
        semester_id=semester_id,
        search="rvce",
    )

    user_query = str(db.queries[1])
    assert "users.role" in user_query
    assert "users.account_status" in user_query
    assert "student_profiles.branch_id" in user_query
    assert "student_profiles.current_semester_id" in user_query
    assert "lower(users.email)" in user_query
    assert "lower(users.full_name)" in user_query
    assert result["page"] == 2
    assert result["page_size"] == 10
    assert result["pages"] == 1


def test_student_is_denied_every_admin_api_group(monkeypatch):
    student = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )
    monkeypatch.setattr(auth_routes, "synchronized_user", lambda db, token: (student, None))

    def fake_current_user():
        return student

    def fake_db():
        yield SimpleNamespace()

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_db] = fake_db
    try:
        client = TestClient(app)
        paths = [
            "/api/v1/admin/syllabus",
            "/api/v1/admin/pyqs",
            "/api/v1/admin/resources",
            "/api/v1/admin/uploads",
            "/api/v1/admin/academic/branches",
            "/api/v1/admin/academic/schemes",
            "/api/v1/admin/academic/semesters",
            "/api/v1/admin/academic/subjects",
            "/api/v1/admin/academic/elective-options",
            "/api/v1/admin/academic/elective-baskets",
            "/api/v1/auth/admin/dashboard",
            "/api/v1/auth/admin/users",
            "/api/v1/auth/admin/profile",
            "/api/v1/auth/admin/academic/branches",
        ]
        for path in paths:
            response = client.get(path, headers={"Authorization": "Bearer test-token"})
            assert response.status_code == 403, path
    finally:
        app.dependency_overrides.clear()


def _download_db(subject_id, enroll=True, lookup=None):
    profile = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    enrollments = (
        [SimpleNamespace(subject_id=subject_id, active=True)] if enroll else []
    )
    return LookupDB(lookup=lookup, scalar_values=[[profile], enrollments])


def _document(subject_id, *, active=True, status=VerificationStatus.VERIFIED):
    return SimpleNamespace(
        id=uuid.uuid4(),
        syllabus_version_id=uuid.uuid4(),
        storage_path="syllabus/path.pdf",
        original_filename="syllabus.pdf",
        active=active,
        verification_status=status,
    )


def _version(subject_id, *, active=True, status=VerificationStatus.VERIFIED):
    return SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject_id,
        active=active,
        verification_status=status,
    )


def test_student_download_denies_unpublished_and_archived_content(monkeypatch):
    subject_id = uuid.uuid4()
    student = SimpleNamespace(id=uuid.uuid4())
    signed = []
    monkeypatch.setattr(
        content_routes.storage,
        "create_signed_url",
        lambda path, **_kwargs: signed.append(path) or "https://signed.example/file",
    )

    draft_doc = _document(subject_id, status=VerificationStatus.DRAFT)
    draft_version = _version(subject_id)
    db = _download_db(subject_id, lookup={draft_doc.id: draft_doc, draft_version.id: draft_version})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("syllabus", draft_doc.id, student, db)
    assert error.value.status_code == 404

    archived_version_doc = _document(subject_id)
    archived_version = _version(subject_id, active=False)
    db = _download_db(
        subject_id,
        lookup={archived_version_doc.id: archived_version_doc, archived_version.id: archived_version},
    )
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("syllabus", archived_version_doc.id, student, db)
    assert error.value.status_code == 404

    paper_doc = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=uuid.uuid4(),
        storage_path="pyq/path.pdf",
        original_filename="paper.pdf",
        active=True,
        verification_status=VerificationStatus.VERIFIED,
        permission_status=PermissionStatus.PENDING,
    )
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=paper_doc.id,
        subject_id=subject_id,
    )
    db = _download_db(subject_id, lookup={paper.id: paper, paper_doc.id: paper_doc})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("pyq", paper.id, student, db)
    assert error.value.status_code == 404

    archived_resource = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject_id,
        storage_path="resource/path.pdf",
        original_filename="resource.pdf",
        active=False,
        verification_status=VerificationStatus.VERIFIED,
    )
    db = _download_db(subject_id, lookup={archived_resource.id: archived_resource})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("resource", archived_resource.id, student, db)
    assert error.value.status_code == 404

    unauthorized_resource = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        storage_path="resource/path.pdf",
        original_filename="resource.pdf",
        active=True,
        verification_status=VerificationStatus.VERIFIED,
    )
    db = _download_db(subject_id, enroll=False, lookup={unauthorized_resource.id: unauthorized_resource})
    with pytest.raises(HTTPException) as error:
        content_routes.student_download("resource", unauthorized_resource.id, student, db)
    assert error.value.status_code == 403
    assert signed == []


def test_authorized_student_download_creates_signed_url(monkeypatch):
    subject_id = uuid.uuid4()
    student = SimpleNamespace(id=uuid.uuid4())
    resource = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject_id,
        storage_path="resource/path.pdf",
        original_filename="resource.pdf",
        active=True,
        verification_status=VerificationStatus.VERIFIED,
    )
    db = _download_db(subject_id, lookup={resource.id: resource})
    monkeypatch.setattr(
        content_routes.storage,
        "create_signed_url",
        lambda path, **_kwargs: "https://signed.example/private",
    )
    result = content_routes.student_download("resource", resource.id, student, db)
    assert result["url"] == "https://signed.example/private"
    assert result["expires_in"] == storage.SIGNED_URL_TTL_SECONDS
    assert result["filename"] == "resource.pdf"


def test_private_storage_bucket_is_created_as_private(monkeypatch):
    created = []

    class BucketAPI:
        def list_buckets(self):
            return []

        def create_bucket(self, name, options=None):
            created.append((name, options))

    class Client:
        storage = BucketAPI()

    monkeypatch.setattr(storage, "create_supabase_service_client", lambda: Client())
    storage.ensure_bucket()
    assert created == [("pyqverse-content", {"public": False})]


def test_admin_upload_update_archive_and_download_syllabus(monkeypatch):
    subject = _subject()
    scheme = _scheme()
    semester = _semester(scheme.id)
    subject.academic_scheme_id = scheme.id
    subject.semester_id = semester.id
    db = LookupDB(lookup={subject.id: subject, scheme.id: scheme, semester.id: semester})
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        content_routes.storage, "create_signed_url", lambda path, **_kwargs: "https://signed.example/syllabus"
    )

    upload = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test"),
        filename="syllabus.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    result = asyncio.run(
        content_routes.admin_upload_syllabus(
            file=upload,
            subject_id=subject.id,
            version="2025-v1",
            title="Semester III Syllabus",
            description="Official syllabus",
            status="VERIFIED",
            admin=_admin(),
            db=db,
        )
    )
    assert result["title"] == "Semester III Syllabus"
    assert result["verification_status"] == "VERIFIED"
    assert db.committed == 1

    document = next(value for value in db.added if isinstance(value, SyllabusDocument))
    version = next(value for value in db.added if isinstance(value, SyllabusVersion))
    db.lookup[document.id] = document
    db.lookup[version.id] = version

    updated = content_routes.admin_update_syllabus(
        document.id,
        SyllabusUpdate(title="Updated title", description="Updated description", status="DRAFT", active=True),
        _admin(),
        db,
    )
    assert updated["title"] == "Updated title"
    assert updated["description"] == "Updated description"
    assert updated["verification_status"] == "DRAFT"
    assert version.verification_status == VerificationStatus.DRAFT

    archived = content_routes.admin_archive_syllabus(document.id, _admin(), db)
    assert archived["message"]
    assert document.active is False
    assert version.active is False

    download = content_routes.admin_download("syllabus", document.id, _admin(), db)
    assert download["url"] == "https://signed.example/syllabus"


def test_admin_upload_update_archive_and_download_pyq(monkeypatch):
    subject = _subject()
    scheme = _scheme()
    semester = _semester(scheme.id)
    subject.academic_scheme_id = scheme.id
    subject.semester_id = semester.id
    db = LookupDB(lookup={subject.id: subject, scheme.id: scheme, semester.id: semester})
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        content_routes.storage, "create_signed_url", lambda path, **_kwargs: "https://signed.example/pyq"
    )

    upload = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test"),
        filename="paper.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    result = asyncio.run(
        content_routes.admin_upload_pyq(
            file=upload,
            subject_id=subject.id,
            exam_type="SEE",
            examination_year=2025,
            cie_number=None,
            title="SEE 2025",
            description="Question paper",
            status="VERIFIED",
            admin=_admin(),
            db=db,
        )
    )
    assert result["title"] == "SEE 2025"
    assert result["verification_status"] == "VERIFIED"

    paper = next(value for value in db.added if isinstance(value, QuestionPaper))
    document = next(value for value in db.added if isinstance(value, UploadedDocument))
    db.lookup[paper.id] = paper
    db.lookup[document.id] = document

    updated = content_routes.admin_update_pyq(
        paper.id,
        PyqUpdate(title="Updated paper", description="Updated description", status="DRAFT", active=True),
        _admin(),
        db,
    )
    assert updated["title"] == "Updated paper"
    assert updated["verification_status"] == "DRAFT"
    assert document.permission_status == PermissionStatus.PENDING

    archived = content_routes.admin_archive_pyq(paper.id, _admin(), db)
    assert archived["message"]
    assert document.active is False

    download = content_routes.admin_download("pyq", paper.id, _admin(), db)
    assert download["url"] == "https://signed.example/pyq"


def test_admin_upload_update_archive_and_download_resource(monkeypatch):
    subject = _subject()
    scheme = _scheme()
    semester = _semester(scheme.id)
    subject.academic_scheme_id = scheme.id
    subject.semester_id = semester.id
    db = LookupDB(lookup={subject.id: subject, scheme.id: scheme, semester.id: semester})
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        content_routes.storage, "create_signed_url", lambda path, **_kwargs: "https://signed.example/resource"
    )

    upload = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 test"),
        filename="notes.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    result = asyncio.run(
        content_routes.admin_upload_resource(
            file=upload,
            subject_id=subject.id,
            resource_type=ResourceType.NOTES.value,
            title="Unit 1 Notes",
            description="Notes",
            status="VERIFIED",
            admin=_admin(),
            db=db,
        )
    )
    assert result["title"] == "Unit 1 Notes"
    assert result["verification_status"] == "VERIFIED"

    resource = next(value for value in db.added if isinstance(value, LearningResource))
    db.lookup[resource.id] = resource

    updated = content_routes.admin_update_resource(
        resource.id,
        ResourceUpdate(
            title="Updated notes",
            description="Updated description",
            resource_type=ResourceType.STUDY_MATERIAL.value,
            status="DRAFT",
            active=True,
        ),
        _admin(),
        db,
    )
    assert updated["title"] == "Updated notes"
    assert updated["resource_type"] == ResourceType.STUDY_MATERIAL.value
    assert updated["verification_status"] == "DRAFT"

    archived = content_routes.admin_archive_resource(resource.id, _admin(), db)
    assert archived["message"]
    assert resource.active is False

    download = content_routes.admin_download("resource", resource.id, _admin(), db)
    assert download["url"] == "https://signed.example/resource"


def _student_query_db(subject_id):
    profile = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    enrollment = SimpleNamespace(subject_id=subject_id, active=True)

    class StudentDB:
        def __init__(self):
            self.scalars_calls = 0
            self.statements = []

        def scalars(self, query):
            self.statements.append(query)
            self.scalars_calls += 1
            if self.scalars_calls == 1:
                return ScalarResult([profile])
            if self.scalars_calls == 2:
                return ScalarResult([enrollment])
            return ScalarResult([])

        def execute(self, query):
            self.statements.append(query)
            return RowResult([])

    return StudentDB()


def test_student_content_lists_filter_to_enrolled_published_rows():
    subject_id = uuid.uuid4()
    student = SimpleNamespace(id=uuid.uuid4())

    syllabus_db = _student_query_db(subject_id)
    content_routes.student_list_syllabus(student=student, db=syllabus_db)
    syllabus_sql = str(syllabus_db.statements[-1])
    assert "syllabus_versions.subject_id" in syllabus_sql
    assert "syllabus_versions.active" in syllabus_sql
    assert "syllabus_versions.verification_status" in syllabus_sql
    assert "syllabus_documents.active" in syllabus_sql
    assert "syllabus_documents.verification_status" in syllabus_sql

    pyq_db = _student_query_db(subject_id)
    content_routes.student_list_pyqs(student=student, db=pyq_db)
    pyq_sql = str(pyq_db.statements[-1])
    assert "question_papers.subject_id" in pyq_sql
    assert "uploaded_documents.active" in pyq_sql
    assert "uploaded_documents.verification_status" in pyq_sql
    assert "uploaded_documents.permission_status" in pyq_sql

    resource_db = _student_query_db(subject_id)
    content_routes.student_list_resources(student=student, db=resource_db)
    resource_sql = str(resource_db.statements[-1])
    assert "learning_resources.subject_id" in resource_sql
    assert "learning_resources.active" in resource_sql
    assert "learning_resources.verification_status" in resource_sql


def test_admin_uploads_hub_reports_all_content_kinds():
    subject = _subject()
    version = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject.id,
        version="2025-v1",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    syllabus_document = SimpleNamespace(
        id=uuid.uuid4(),
        title="Syllabus",
        original_filename="syllabus.pdf",
        verification_status=VerificationStatus.VERIFIED,
        active=True,
        file_size=100,
    )
    paper = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject.id,
        title="PYQ",
    )
    pyq_document = SimpleNamespace(
        id=uuid.uuid4(),
        title=None,
        original_filename="paper.pdf",
        verification_status=VerificationStatus.DRAFT,
        active=True,
        uploaded_at=datetime(2026, 1, 2, 12, 0, 0),
        file_size=200,
    )
    resource = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject.id,
        title="Notes",
        verification_status=VerificationStatus.VERIFIED,
        active=False,
        uploaded_at=datetime(2026, 1, 3, 12, 0, 0),
        file_size=300,
    )

    class HubDB:
        def __init__(self):
            self.execute_calls = 0
            self.scalars_calls = 0

        def execute(self, _query):
            self.execute_calls += 1
            if self.execute_calls == 1:
                return RowResult([(version, syllabus_document)])
            return RowResult([(paper, pyq_document)])

        def scalars(self, _query):
            self.scalars_calls += 1
            if self.scalars_calls == 1:
                return ScalarResult([resource])
            return ScalarResult([subject])

    result = content_routes.admin_uploads(admin=_admin(), db=HubDB(), limit=50)
    assert {item["kind"] for item in result["items"]} == {"SYLLABUS", "PYQ", "RESOURCE"}
    assert result["total"] == 3


def test_admin_syllabus_listing_returns_legacy_content():
    subject = _subject()
    version = SimpleNamespace(
        id=uuid.uuid4(),
        subject_id=subject.id,
        version="2025-v1",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        verification_status=VerificationStatus.DRAFT,
        active=True,
    )
    document = SimpleNamespace(
        id=uuid.uuid4(),
        title="Syllabus",
        description="Legacy syllabus record",
        original_filename="syllabus.pdf",
        file_type="pdf",
        file_size=100,
        verification_status=VerificationStatus.DRAFT,
        active=True,
    )

    class SyllabusListDB:
        def execute(self, _query):
            return RowResult([(version, document)])

        def scalars(self, _query):
            return ScalarResult([subject])

    result = content_routes.admin_list_syllabus(admin=_admin(), db=SyllabusListDB())

    assert result["total"] == 1
    assert result["items"][0]["subject_code"] == subject.code
    assert result["items"][0]["verification_status"] == "DRAFT"
    assert result["items"][0]["title"] == "Syllabus"
