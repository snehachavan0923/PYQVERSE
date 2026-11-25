import asyncio
import io
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers, UploadFile

from app.api import content_routes
from app.models.academic import AcademicScheme, Semester, Subject
from app.models.document import QuestionPaper, UploadedDocument
from app.models.syllabus import VerificationStatus
from app.schemas.content import PyqUpdate


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values[0] if self.values else None


class RowResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class SharedState:
    def __init__(self):
        self.records = []
        self.lock = threading.Lock()
        self.subject = SimpleNamespace(
            id=uuid.uuid4(),
            code="CS233AI",
            name="Data Structures",
            active=True,
            academic_scheme_id=uuid.uuid4(),
            semester_id=uuid.uuid4(),
        )
        self.scheme = SimpleNamespace(id=self.subject.academic_scheme_id)
        self.semester = SimpleNamespace(id=self.subject.semester_id)


class FakeDatabase:
    def __init__(self, state, duplicate_check_barrier=None):
        self.state = state
        self.pending = []
        self.locked = False
        self.duplicate_check_barrier = duplicate_check_barrier

    def get(self, model, object_id):
        if model is Subject and object_id == self.state.subject.id:
            return self.state.subject
        if model is AcademicScheme and object_id == self.state.scheme.id:
            return self.state.scheme
        if model is Semester and object_id == self.state.semester.id:
            return self.state.semester
        for paper, document in self.state.records:
            if model is QuestionPaper and paper.id == object_id:
                return paper
            if model is UploadedDocument and document.id == object_id:
                return document
        return None

    def execute(self, statement):
        file_size = next(
            value for key, value in statement.compile().params.items() if "file_size" in key
        )
        matching = [
            (paper, document)
            for paper, document in self.state.records
            if document.content_sha256 is None
            and document.active
            and document.file_type == "pdf"
            and document.file_size == file_size
        ]
        if self.duplicate_check_barrier is not None:
            self.duplicate_check_barrier.wait()
        return RowResult(matching)

    def scalars(self, statement):
        params = statement.compile().params
        content_hash = next(
            value for key, value in params.items() if "content_sha256" in key
        )
        matching = [
            paper
            for paper, document in self.state.records
            if document.active and document.content_sha256 == content_hash
        ]
        return ScalarResult(matching)

    def add(self, value):
        self.pending.append(value)

    def flush(self):
        for value in self.pending:
            if value.id is None:
                value.id = uuid.uuid4()

    def commit(self):
        self.state.lock.acquire()
        try:
            self.flush()
            documents = [item for item in self.pending if isinstance(item, UploadedDocument)]
            candidate_documents = [
                document
                for _paper, document in self.state.records
            ] + documents
            active_hashes = set()
            for document in candidate_documents:
                if not document.active or not document.content_sha256:
                    continue
                if document.content_sha256 in active_hashes:
                    raise IntegrityError(
                        "insert",
                        {},
                        SimpleNamespace(
                            diag=SimpleNamespace(
                                constraint_name="uq_uploaded_documents_active_content_sha256"
                            )
                        ),
                    )
                active_hashes.add(document.content_sha256)
            for paper in (item for item in self.pending if isinstance(item, QuestionPaper)):
                document = next(item for item in documents if item.id == paper.uploaded_document_id)
                self.state.records.append((paper, document))
            self.pending.clear()
        finally:
            self.state.lock.release()

    def rollback(self):
        self.pending.clear()

    def refresh(self, _value):
        return None


def _upload(state, data, filename="paper.pdf", duplicate_check_barrier=None):
    file = UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )
    return asyncio.run(
        content_routes.admin_upload_pyq(
            file=file,
            subject_id=state.subject.id,
            exam_type="SEE",
            examination_year=2025,
            cie_number=None,
            title="SEE 2025",
            description=None,
            status="DRAFT",
            admin=SimpleNamespace(id=uuid.uuid4()),
            db=FakeDatabase(state, duplicate_check_barrier=duplicate_check_barrier),
        )
    )


def test_identical_pdf_content_is_rejected_even_with_different_filename(monkeypatch):
    state = SharedState()
    uploaded = []
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda path, *_args: uploaded.append(path))
    data = b"%PDF-1.4 same bytes"

    _upload(state, data)
    with pytest.raises(HTTPException) as error:
        _upload(state, data, filename="renamed.pdf")

    assert error.value.status_code == 409
    assert error.value.detail == "An active question paper with identical PDF content already exists"
    assert len(uploaded) == 1


def test_different_pdfs_with_same_filename_and_metadata_are_allowed(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *_args: None)

    first = _upload(state, b"%PDF-1.4 first paper")
    second = _upload(state, b"%PDF-1.4 second paper")

    assert first["id"] != second["id"]
    assert len(state.records) == 2
    assert all(document.content_sha256 for _paper, document in state.records)


def test_identical_legacy_pdf_is_detected_without_modifying_its_record(monkeypatch):
    state = SharedState()
    data = b"%PDF-1.4 legacy question paper"
    old_document = SimpleNamespace(
        id=uuid.uuid4(),
        active=True,
        content_sha256=None,
        file_type="pdf",
        file_size=len(data),
        storage_path="pyq/legacy/paper.pdf",
    )
    old_paper = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=old_document.id,
    )
    state.records.append((old_paper, old_document))
    uploaded = []
    monkeypatch.setattr(content_routes.storage, "download_bytes", lambda _path: data)
    monkeypatch.setattr(
        content_routes.storage, "upload_bytes", lambda path, *_args: uploaded.append(path)
    )

    with pytest.raises(HTTPException) as error:
        _upload(state, data, filename="renamed.pdf")

    assert error.value.status_code == 409
    assert old_document.content_sha256 is None
    assert uploaded == []


def test_archived_pdf_does_not_block_reupload(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *_args: None)
    data = b"%PDF-1.4 archived paper"
    uploaded = _upload(state, data)
    paper = state.records[0][0]

    result = content_routes.admin_archive_pyq(
        paper.id,
        SimpleNamespace(id=uuid.uuid4()),
        FakeDatabase(state),
    )
    reuploaded = _upload(state, data)

    assert result["message"] == "Question paper archived"
    assert state.records[0][1].active is False
    assert reuploaded["id"] != uploaded["id"]
    assert len(state.records) == 2


def test_archived_legacy_pdf_is_not_compared_as_an_active_duplicate(monkeypatch):
    state = SharedState()
    data = b"%PDF-1.4 archived legacy paper"
    old_document = SimpleNamespace(
        id=uuid.uuid4(),
        active=False,
        content_sha256=None,
        file_type="pdf",
        file_size=len(data),
        storage_path="pyq/legacy/archived.pdf",
    )
    old_paper = SimpleNamespace(
        id=uuid.uuid4(),
        uploaded_document_id=old_document.id,
    )
    state.records.append((old_paper, old_document))
    monkeypatch.setattr(content_routes.storage, "download_bytes", lambda _path: data)
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *_args: None)

    result = _upload(state, data)

    assert result["id"] != str(old_paper.id)
    assert len(state.records) == 2


def test_archived_pdf_cannot_be_restored_if_identical_active_copy_exists(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(content_routes.storage, "upload_bytes", lambda *_args: None)
    data = b"%PDF-1.4 restorable paper"
    _upload(state, data)
    archived_paper, _archived_document = state.records[0]
    content_routes.admin_archive_pyq(
        archived_paper.id,
        SimpleNamespace(id=uuid.uuid4()),
        FakeDatabase(state),
    )
    _upload(state, data)

    with pytest.raises(HTTPException) as error:
        content_routes.admin_update_pyq(
            archived_paper.id,
            PyqUpdate(active=True),
            SimpleNamespace(id=uuid.uuid4()),
            FakeDatabase(state),
        )

    assert error.value.status_code == 409
    assert state.records[0][1].active is False
    assert state.records[1][1].active is True


def test_concurrent_identical_uploads_create_only_one_active_record(monkeypatch):
    state = SharedState()
    uploads = []
    deletions = []
    duplicate_check_barrier = threading.Barrier(2)
    monkeypatch.setattr(
        content_routes.storage,
        "upload_bytes",
        lambda path, *_args: uploads.append(path),
    )
    monkeypatch.setattr(
        content_routes.storage,
        "delete_object",
        lambda path: deletions.append(path),
    )
    data = b"%PDF-1.4 concurrent paper"

    def attempt():
        try:
            _upload(state, data, duplicate_check_barrier=duplicate_check_barrier)
            return "created"
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: attempt(), range(2)))

    assert sorted(results, key=str) == [409, "created"]
    assert len(state.records) == 1

    active_documents = [
        document for _paper, document in state.records if document.active
    ]
    assert len(active_documents) == 1

    assert len(uploads) == 2
    assert len(deletions) == 1
    survivor_path = active_documents[0].storage_path
    assert survivor_path in uploads
    assert deletions[0] in uploads
    assert deletions[0] != survivor_path
    assert set(uploads) == {deletions[0], survivor_path}
