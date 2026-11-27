import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import content_routes
from app.api.deps import get_current_user
from app.database.connection import get_db
from app.main import app
from app.models.document import ExamType, PermissionStatus, QuestionPaper, UploadedDocument
from app.models.question import DocumentPage, Question, QuestionOccurrence
from app.models.resource import LearningResource
from app.models.syllabus import SyllabusDocument, SyllabusVersion, Unit, VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.services.storage import StorageError


def _admin():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Admin Faculty",
        email="admin@rvce.edu.in",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


def _student():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Student User",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


class MockDB:
    """In-memory mock database session for content deletion testing."""

    def __init__(self, entities=None):
        self.entities = entities or {}
        self.deleted = []
        self.committed = 0

    def get(self, model, key):
        return self.entities.get((model, key))

    def scalars(self, query):
        q_str = str(query)
        result = [
            obj for (m, _k), obj in self.entities.items()
            if getattr(m, "__tablename__", "") in q_str
        ]
        return SimpleNamespace(all=lambda: list(result), first=lambda: result[0] if result else None)

    def scalar(self, query):
        q_str = str(query).lower()

        if "storage_path" in q_str:
            from collections import Counter
            storage_paths = [
                getattr(obj, "storage_path", None)
                for (_m, _k), obj in self.entities.items()
                if getattr(obj, "storage_path", None)
            ]
            counts = Counter(storage_paths)
            return 1 if any(c > 1 for c in counts.values()) else 0

        if "questions" in q_str and "question_occurrences" not in q_str:
            return sum(1 for (m, _k) in self.entities if m is Question)
        if "question_occurrences" in q_str:
            return sum(1 for (m, _k) in self.entities if m is QuestionOccurrence)
        if "units" in q_str:
            return sum(1 for (m, _k) in self.entities if m is Unit)
        if "syllabus_documents" in q_str:
            syl_docs = [obj for (m, _k), obj in self.entities.items() if m is SyllabusDocument]
            return len(syl_docs) - 1 if len(syl_docs) > 1 else 0

        return 0

    def delete(self, obj):
        self.deleted.append(obj)
        for k, v in list(self.entities.items()):
            if v is obj:
                del self.entities[k]

    def commit(self):
        self.committed += 1

    def rollback(self):
        pass


# -----------------------------------------------------------------------------
# 1. Access Control: Students cannot delete content via API
# -----------------------------------------------------------------------------
def test_student_cannot_delete_any_content_via_api():
    student = _student()
    app.dependency_overrides[get_current_user] = lambda: student
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()

    try:
        client = TestClient(app)
        test_id = uuid.uuid4()
        endpoints = [
            f"/api/v1/admin/pyqs/{test_id}",
            f"/api/v1/admin/pyqs/{test_id}?permanent=true",
            f"/api/v1/admin/pyqs/{test_id}/permanent",
            f"/api/v1/admin/syllabus/{test_id}",
            f"/api/v1/admin/syllabus/{test_id}?permanent=true",
            f"/api/v1/admin/syllabus/{test_id}/permanent",
            f"/api/v1/admin/resources/{test_id}",
            f"/api/v1/admin/resources/{test_id}?permanent=true",
            f"/api/v1/admin/resources/{test_id}/permanent",
            f"/api/v1/admin/documents/{test_id}",
            f"/api/v1/admin/content/pyq/{test_id}",
            f"/api/v1/admin/content/syllabus/{test_id}",
            f"/api/v1/admin/content/resource/{test_id}",
            f"/api/v1/admin/content/document/{test_id}",
        ]
        for url in endpoints:
            res = client.delete(url, headers={"Authorization": "Bearer test-token"})
            assert res.status_code == 403, f"Expected 403 Forbidden for {url}, got {res.status_code}"
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_user_cannot_delete_content():
    client = TestClient(app)
    test_id = uuid.uuid4()
    res = client.delete(f"/api/v1/admin/pyqs/{test_id}")
    assert res.status_code == 401


# -----------------------------------------------------------------------------
# 2. PYQ Deletion
# -----------------------------------------------------------------------------
def test_admin_delete_pyq_success(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    paper_id = uuid.uuid4()
    storage_path = "pyq/2024/test_paper.pdf"

    document = SimpleNamespace(
        id=doc_id,
        storage_path=storage_path,
        active=True,
    )
    paper = SimpleNamespace(
        id=paper_id,
        uploaded_document_id=doc_id,
    )

    db = MockDB({
        (QuestionPaper, paper_id): paper,
        (UploadedDocument, doc_id): document,
    })

    result = content_routes._delete_pyq_core(db, paper_id)
    assert result["message"] == "Question paper deleted successfully"
    assert result["id"] == str(paper_id)
    assert paper in db.deleted
    assert document in db.deleted
    assert db.committed == 1
    mock_storage.assert_called_once_with(storage_path)


def test_admin_delete_pyq_blocked_by_dependent_questions(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    paper_id = uuid.uuid4()
    document = SimpleNamespace(id=doc_id, storage_path="pyq/test.pdf")
    paper = SimpleNamespace(id=paper_id, uploaded_document_id=doc_id)
    question = SimpleNamespace(id=uuid.uuid4(), document_id=doc_id)

    db = MockDB({
        (QuestionPaper, paper_id): paper,
        (UploadedDocument, doc_id): document,
        (Question, question.id): question,
    })

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_pyq_core(db, paper_id)

    assert exc_info.value.status_code == 409
    assert "extracted question(s) depend on this document" in exc_info.value.detail
    assert len(db.deleted) == 0
    mock_storage.assert_not_called()


def test_admin_delete_pyq_blocked_by_dependent_occurrences(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    paper_id = uuid.uuid4()
    document = SimpleNamespace(id=doc_id, storage_path="pyq/test.pdf")
    paper = SimpleNamespace(id=paper_id, uploaded_document_id=doc_id)
    occ = SimpleNamespace(id=uuid.uuid4(), document_id=doc_id)

    db = MockDB({
        (QuestionPaper, paper_id): paper,
        (UploadedDocument, doc_id): document,
        (QuestionOccurrence, occ.id): occ,
    })

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_pyq_core(db, paper_id)

    assert exc_info.value.status_code == 409
    assert "question occurrence reference(s) depend on this document" in exc_info.value.detail
    assert len(db.deleted) == 0
    mock_storage.assert_not_called()


# -----------------------------------------------------------------------------
# 3. Syllabus Deletion
# -----------------------------------------------------------------------------
def test_admin_delete_syllabus_document_and_version(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    storage_path = "syllabus/2024/test_syllabus.pdf"

    document = SimpleNamespace(
        id=doc_id,
        syllabus_version_id=version_id,
        storage_path=storage_path,
    )
    version = SimpleNamespace(
        id=version_id,
    )

    db = MockDB({
        (SyllabusDocument, doc_id): document,
        (SyllabusVersion, version_id): version,
    })

    result = content_routes._delete_syllabus_core(db, doc_id)
    assert result["message"] == "Syllabus document deleted successfully"
    assert document in db.deleted
    assert version in db.deleted
    assert db.committed == 1
    mock_storage.assert_called_once_with(storage_path)


def test_admin_delete_syllabus_blocked_by_dependent_units(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document = SimpleNamespace(id=doc_id, syllabus_version_id=version_id, storage_path="syl.pdf")
    version = SimpleNamespace(id=version_id)
    unit = SimpleNamespace(id=uuid.uuid4(), syllabus_version_id=version_id)

    db = MockDB({
        (SyllabusDocument, doc_id): document,
        (SyllabusVersion, version_id): version,
        (Unit, unit.id): unit,
    })

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_syllabus_core(db, doc_id)

    assert exc_info.value.status_code == 409
    assert "syllabus unit(s) are mapped to this version" in exc_info.value.detail
    assert len(db.deleted) == 0
    mock_storage.assert_not_called()


# -----------------------------------------------------------------------------
# 4. Learning Resource Deletion
# -----------------------------------------------------------------------------
def test_admin_delete_learning_resource(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    res_id = uuid.uuid4()
    storage_path = "resources/2024/notes.pdf"
    resource = SimpleNamespace(id=res_id, storage_path=storage_path)

    db = MockDB({
        (LearningResource, res_id): resource,
    })

    result = content_routes._delete_resource_core(db, res_id)
    assert result["message"] == "Learning resource deleted successfully"
    assert resource in db.deleted
    assert db.committed == 1
    mock_storage.assert_called_once_with(storage_path)


# -----------------------------------------------------------------------------
# 5. Standalone Document Deletion
# -----------------------------------------------------------------------------
def test_admin_delete_standalone_document(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    doc_id = uuid.uuid4()
    storage_path = "documents/standalone.pdf"
    document = SimpleNamespace(id=doc_id, storage_path=storage_path)

    db = MockDB({
        (UploadedDocument, doc_id): document,
    })

    result = content_routes._delete_document_core(db, doc_id)
    assert result["message"] == "Document deleted successfully"
    assert document in db.deleted
    assert db.committed == 1
    mock_storage.assert_called_once_with(storage_path)


# -----------------------------------------------------------------------------
# 6. Shared Storage Preservation
# -----------------------------------------------------------------------------
def test_shared_storage_path_is_not_deleted(monkeypatch):
    mock_storage = MagicMock()
    monkeypatch.setattr(content_routes.storage, "delete_object", mock_storage)

    shared_path = "shared/content.pdf"
    res1_id = uuid.uuid4()
    res2_id = uuid.uuid4()

    resource1 = SimpleNamespace(id=res1_id, storage_path=shared_path)
    resource2 = SimpleNamespace(id=res2_id, storage_path=shared_path)

    db = MockDB({
        (LearningResource, res1_id): resource1,
        (LearningResource, res2_id): resource2,
    })

    result = content_routes._delete_resource_core(db, res1_id)
    assert result["message"] == "Learning resource deleted successfully"
    assert resource1 in db.deleted
    # Storage file MUST NOT be deleted because resource2 still references it!
    mock_storage.assert_not_called()


# -----------------------------------------------------------------------------
# 7. Missing Storage File Resilience
# -----------------------------------------------------------------------------
def test_missing_storage_file_handled_safely(monkeypatch):
    def fake_delete_object(path):
        raise StorageError("Object not found in storage bucket")

    monkeypatch.setattr(content_routes.storage, "delete_object", fake_delete_object)

    res_id = uuid.uuid4()
    resource = SimpleNamespace(id=res_id, storage_path="missing/file.pdf")

    db = MockDB({
        (LearningResource, res_id): resource,
    })

    # Should succeed without raising 500 error
    result = content_routes._delete_resource_core(db, res_id)
    assert result["message"] == "Learning resource deleted successfully"
    assert resource in db.deleted
    assert db.committed == 1


# -----------------------------------------------------------------------------
# 8. Not Found 404
# -----------------------------------------------------------------------------
def test_delete_nonexistent_content_returns_404():
    db = MockDB()
    non_existent = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_pyq_core(db, non_existent)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_syllabus_core(db, non_existent)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_resource_core(db, non_existent)
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        content_routes._delete_document_core(db, non_existent)
    assert exc_info.value.status_code == 404


# -----------------------------------------------------------------------------
# 9. Unified Endpoint Routing
# -----------------------------------------------------------------------------
def test_unified_admin_delete_content_endpoint(monkeypatch):
    mock_admin = _admin()
    test_id = uuid.uuid4()

    monkeypatch.setattr(content_routes, "_delete_pyq_core", lambda db, cid: {"message": "pyq", "id": str(cid)})
    monkeypatch.setattr(content_routes, "_delete_syllabus_core", lambda db, cid: {"message": "syllabus", "id": str(cid)})
    monkeypatch.setattr(content_routes, "_delete_resource_core", lambda db, cid: {"message": "resource", "id": str(cid)})
    monkeypatch.setattr(content_routes, "_delete_document_core", lambda db, cid: {"message": "document", "id": str(cid)})

    db = MockDB()
    assert content_routes.admin_delete_content("pyq", test_id, mock_admin, db)["message"] == "pyq"
    assert content_routes.admin_delete_content("syllabus", test_id, mock_admin, db)["message"] == "syllabus"
    assert content_routes.admin_delete_content("resource", test_id, mock_admin, db)["message"] == "resource"
    assert content_routes.admin_delete_content("document", test_id, mock_admin, db)["message"] == "document"

    with pytest.raises(HTTPException) as exc_info:
        content_routes.admin_delete_content("unknown_kind", test_id, mock_admin, db)
    assert exc_info.value.status_code == 400
