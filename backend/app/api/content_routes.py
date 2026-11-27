from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_student
from app.database.connection import get_db
from app.models.academic import (
    AcademicScheme,
    BranchSubjectOffering,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.analysis import AnalysisJob, AnalysisJobStatus
from app.models.document import ExamType, PermissionStatus, QuestionPaper, UploadedDocument
from app.models.question import DocumentPage, Question, QuestionOccurrence
from app.models.resource import LearningResource, ResourceType
from app.models.syllabus import SyllabusDocument, SyllabusVersion, Unit, VerificationStatus
from app.models.user import User
from app.schemas.content import PyqUpdate, ResourceUpdate, SyllabusUpdate
from app.services import storage
from app.services.content import (
    MAX_FILE_BYTES,
    clean_text,
    safe_object_path,
    safe_original_filename,
    validate_external_url,
    validate_file,
)
from app.services.pyq_analyzer import run_pyq_analysis_job

router = APIRouter(tags=["content"])
logger = logging.getLogger(__name__)

VALID_STATUSES = {status.value for status in VerificationStatus}
RESOURCE_TYPES = {item.value for item in ResourceType}
PYQ_HASH_CONSTRAINT = "uq_uploaded_documents_active_content_sha256"


# ----------------------------------------------------------------- helpers
async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The uploaded file exceeds the 20 MB limit")
    return data


def _status(value: str | None, default: VerificationStatus = VerificationStatus.DRAFT) -> VerificationStatus:
    normalized = (value or default.value).strip().upper()
    if normalized not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid publication status")
    return VerificationStatus(normalized)


def _subject_or_400(db: Session, subject_id: uuid.UUID) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.active:
        raise HTTPException(status_code=400, detail="Select a valid, active subject")
    return subject


def _cleanup(path: str | None) -> None:
    if not path:
        return
    try:
        storage.delete_object(path)
    except Exception:
        # Best-effort cleanup; failed uploads must not break the request path.
        pass


def _is_storage_path_shared(
    db: Session,
    storage_path: str,
    *,
    exclude_upload_doc_id: uuid.UUID | None = None,
    exclude_syllabus_doc_id: uuid.UUID | None = None,
    exclude_resource_id: uuid.UUID | None = None,
) -> bool:
    """Check if another document or resource record shares this storage path."""
    if not storage_path:
        return False

    # Check UploadedDocument
    up_stmt = select(func.count(UploadedDocument.id)).where(UploadedDocument.storage_path == storage_path)
    if exclude_upload_doc_id is not None:
        up_stmt = up_stmt.where(UploadedDocument.id != exclude_upload_doc_id)
    if (db.scalar(up_stmt) or 0) > 0:
        return True

    # Check SyllabusDocument
    syl_stmt = select(func.count(SyllabusDocument.id)).where(SyllabusDocument.storage_path == storage_path)
    if exclude_syllabus_doc_id is not None:
        syl_stmt = syl_stmt.where(SyllabusDocument.id != exclude_syllabus_doc_id)
    if (db.scalar(syl_stmt) or 0) > 0:
        return True

    # Check LearningResource
    res_stmt = select(func.count(LearningResource.id)).where(LearningResource.storage_path == storage_path)
    if exclude_resource_id is not None:
        res_stmt = res_stmt.where(LearningResource.id != exclude_resource_id)
    if (db.scalar(res_stmt) or 0) > 0:
        return True

    return False


def _delete_storage_safely(storage_path: str | None) -> bool:
    """Remove storage file, handling missing files or transient storage errors safely."""
    if not storage_path:
        return True
    try:
        storage.delete_object(storage_path)
        return True
    except Exception as exc:
        logger.warning("Storage file %s deletion error (handled safely): %s", storage_path, exc)
        return False


def _delete_pyq_core(db: Session, paper_id: uuid.UUID) -> dict:
    paper = db.get(QuestionPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Question paper not found")

    document = db.get(UploadedDocument, paper.uploaded_document_id)
    storage_path = None
    is_shared = False

    if document is not None:
        # Check for dependent Question records
        q_count = db.scalar(
            select(func.count(Question.id)).where(Question.document_id == document.id)
        ) or 0
        if q_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete question paper: {q_count} extracted question(s) depend on this document. Remove or reassign them first.",
            )

        # Check for dependent QuestionOccurrence records
        occ_count = db.scalar(
            select(func.count(QuestionOccurrence.id)).where(QuestionOccurrence.document_id == document.id)
        ) or 0
        if occ_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete question paper: {occ_count} question occurrence reference(s) depend on this document.",
            )

        # Remove cached document pages (belong only to this document)
        pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id)).all()
        for p in pages:
            db.delete(p)

        # Remove any analysis jobs for this paper
        jobs = db.scalars(select(AnalysisJob).where(AnalysisJob.question_paper_id == paper.id)).all()
        for j in jobs:
            db.delete(j)

        storage_path = document.storage_path
        is_shared = _is_storage_path_shared(db, storage_path, exclude_upload_doc_id=document.id)

    db.delete(paper)
    if document is not None:
        db.delete(document)
    db.commit()

    if storage_path and not is_shared:
        _delete_storage_safely(storage_path)

    return {"message": "Question paper deleted successfully", "id": str(paper_id)}


def _delete_syllabus_core(db: Session, document_id: uuid.UUID) -> dict:
    document = db.get(SyllabusDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Syllabus document not found")

    version = db.get(SyllabusVersion, document.syllabus_version_id)
    other_docs_count = db.scalar(
        select(func.count(SyllabusDocument.id)).where(
            SyllabusDocument.syllabus_version_id == document.syllabus_version_id,
            SyllabusDocument.id != document.id,
        )
    ) or 0

    delete_version = False
    if other_docs_count == 0 and version is not None:
        unit_count = db.scalar(
            select(func.count(Unit.id)).where(Unit.syllabus_version_id == version.id)
        ) or 0
        if unit_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot delete syllabus document: {unit_count} syllabus unit(s) are mapped to this version. Remove or reassign units first.",
            )
        delete_version = True

    storage_path = document.storage_path
    is_shared = _is_storage_path_shared(db, storage_path, exclude_syllabus_doc_id=document.id)

    db.delete(document)
    if delete_version and version is not None:
        db.delete(version)
    db.commit()

    if storage_path and not is_shared:
        _delete_storage_safely(storage_path)

    return {"message": "Syllabus document deleted successfully", "id": str(document_id)}


def _delete_resource_core(db: Session, resource_id: uuid.UUID) -> dict:
    resource = db.get(LearningResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Learning resource not found")

    storage_path = resource.storage_path
    is_shared = _is_storage_path_shared(db, storage_path, exclude_resource_id=resource.id)

    db.delete(resource)
    db.commit()

    if storage_path and not is_shared:
        _delete_storage_safely(storage_path)

    return {"message": "Learning resource deleted successfully", "id": str(resource_id)}


def _delete_document_core(db: Session, document_id: uuid.UUID) -> dict:
    document = db.get(UploadedDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    paper = db.scalars(
        select(QuestionPaper).where(QuestionPaper.uploaded_document_id == document.id)
    ).first()
    if paper is not None:
        return _delete_pyq_core(db, paper.id)

    q_count = db.scalar(
        select(func.count(Question.id)).where(Question.document_id == document.id)
    ) or 0
    if q_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete document: {q_count} extracted question(s) depend on it. Remove them first.",
        )

    occ_count = db.scalar(
        select(func.count(QuestionOccurrence.id)).where(QuestionOccurrence.document_id == document.id)
    ) or 0
    if occ_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete document: {occ_count} question occurrence reference(s) depend on it.",
        )

    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id)).all()
    for p in pages:
        db.delete(p)

    storage_path = document.storage_path
    is_shared = _is_storage_path_shared(db, storage_path, exclude_upload_doc_id=document.id)

    db.delete(document)
    db.commit()

    if storage_path and not is_shared:
        _delete_storage_safely(storage_path)

    return {"message": "Document deleted successfully", "id": str(document_id)}


def _subject_context(db: Session, subject: Subject) -> tuple[AcademicScheme, Semester]:
    scheme = db.get(AcademicScheme, subject.academic_scheme_id)
    semester = db.get(Semester, subject.semester_id)
    if scheme is None or semester is None:
        raise HTTPException(status_code=400, detail="The subject academic context is incomplete")
    return scheme, semester


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _active_pyq_with_hash(
    db: Session,
    content_sha256: str,
    *,
    exclude_paper_id: uuid.UUID | None = None,
) -> QuestionPaper | None:
    statement = (
        select(QuestionPaper)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            UploadedDocument.content_sha256 == content_sha256,
            UploadedDocument.active.is_(True),
        )
    )
    if exclude_paper_id is not None:
        statement = statement.where(QuestionPaper.id != exclude_paper_id)
    return db.scalars(statement).first()


def _legacy_active_pyqs_same_size(db: Session, file_size: int):
    statement = (
        select(QuestionPaper, UploadedDocument)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            UploadedDocument.content_sha256.is_(None),
            UploadedDocument.active.is_(True),
            UploadedDocument.file_type == "pdf",
            UploadedDocument.file_size == file_size,
        )
    )
    return db.execute(statement).all()


def _is_active_pyq_hash_conflict(exc: IntegrityError) -> bool:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == PYQ_HASH_CONSTRAINT


def _matches_legacy_pyq(db: Session, file_size: int, content_sha256: str) -> bool:
    for _paper, document in _legacy_active_pyqs_same_size(db, file_size):
        try:
            existing_data = storage.download_bytes(document.storage_path)
        except storage.StorageError as exc:
            raise HTTPException(
                status_code=503,
                detail="An existing question paper could not be verified. Please retry later.",
            ) from exc
        if hashlib.sha256(existing_data).hexdigest() == content_sha256:
            return True
    return False


def _syllabus_payload(
    version: SyllabusVersion, document: SyllabusDocument, subject: Subject | None
) -> dict:
    return {
        "id": str(document.id),
        "version_id": str(version.id),
        "subject_id": str(version.subject_id),
        "subject_code": subject.code if subject else None,
        "subject_name": subject.name if subject else None,
        "version": version.version,
        "title": document.title or document.original_filename,
        "description": document.description,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "verification_status": document.verification_status.value,
        "active": document.active,
        "created_at": _iso(version.created_at),
    }


def _pyq_payload(paper: QuestionPaper, document: UploadedDocument, subject: Subject | None) -> dict:
    return {
        "id": str(paper.id),
        "document_id": str(document.id),
        "subject_id": str(paper.subject_id),
        "subject_code": subject.code if subject else None,
        "subject_name": subject.name if subject else None,
        "title": paper.title or document.title or document.original_filename,
        "description": paper.description or document.description,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "exam_type": paper.exam_type.value,
        "cie_number": paper.cie_number,
        "examination_year": paper.examination_year,
        "verification_status": document.verification_status.value,
        "active": document.active,
        "uploaded_at": _iso(document.uploaded_at),
        "uploaded_by": str(document.uploaded_by),
    }


def _resource_payload(
    resource: LearningResource,
    subject: Subject | None,
    unit: Unit | None = None,
) -> dict:
    return {
        "id": str(resource.id),
        "subject_id": str(resource.subject_id),
        "subject_code": subject.code if subject else None,
        "subject_name": subject.name if subject else None,
        "unit_id": str(resource.unit_id) if getattr(resource, "unit_id", None) else None,
        "unit_number": unit.order_index if unit else None,
        "unit_title": unit.title if unit else None,
        "title": resource.title,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "resource_source": getattr(resource, "resource_source", "FILE") or "FILE",
        "external_url": getattr(resource, "external_url", None),
        "link_title": getattr(resource, "link_title", None),
        "original_filename": resource.original_filename,
        "file_type": resource.file_type,
        "file_size": resource.file_size,
        "verification_status": resource.verification_status.value,
        "active": resource.active,
        "uploaded_at": _iso(resource.uploaded_at),
        "uploaded_by": str(resource.uploaded_by) if resource.uploaded_by else None,
    }


def _units_map(db: Session, unit_ids: set[uuid.UUID]) -> dict[uuid.UUID, Unit]:
    valid_ids = {u for u in unit_ids if u is not None}
    if not valid_ids:
        return {}
    return {item.id: item for item in db.scalars(select(Unit).where(Unit.id.in_(valid_ids))).all()}


def _subjects_map(db: Session, subject_ids: set[uuid.UUID]) -> dict[uuid.UUID, Subject]:
    if not subject_ids:
        return {}
    return {item.id: item for item in db.scalars(select(Subject).where(Subject.id.in_(subject_ids))).all()}


# ------------------------------------------------------------ admin syllabus
@router.get("/api/v1/admin/syllabus")
def admin_list_syllabus(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
):
    statement = select(SyllabusVersion, SyllabusDocument).join(
        SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id
    )
    if subject_id:
        statement = statement.where(SyllabusVersion.subject_id == subject_id)
    rows = db.execute(statement.order_by(SyllabusVersion.created_at.desc())).all()
    subjects = _subjects_map(db, {version.subject_id for version, _ in rows})
    items = []
    for version, document in rows:
        subject = subjects.get(version.subject_id)
        if subject is None:
            continue
        if search:
            needle = search.strip().lower()
            haystack = f"{subject.code} {subject.name} {document.original_filename} {version.version}".lower()
            if needle not in haystack:
                continue
        items.append(_syllabus_payload(version, document, subject))
    return {"items": items, "total": len(items)}


@router.post("/api/v1/admin/syllabus", status_code=201)
async def admin_upload_syllabus(
    file: UploadFile = File(...),
    subject_id: uuid.UUID = Form(...),
    version: str = Form(...),
    title: str | None = Form(default=None),
    description: str | None = Form(default=None),
    status: str = Form(default="DRAFT"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subject = _subject_or_400(db, subject_id)
    scheme, _semester = _subject_context(db, subject)
    publication = _status(status)
    version_label = clean_text(version, field="Version", max_length=50, required=True)
    clean_title = clean_text(title, field="Title", max_length=300)
    clean_description = clean_text(description, field="Description", max_length=4000)

    data = await _read_upload(file)
    extension, mime = validate_file(
        category="syllabus",
        filename=file.filename,
        content_type=file.content_type,
        size=len(data),
    )
    path = safe_object_path("syllabus", scheme_id=scheme.id, subject_id=subject.id, extension=extension)
    storage.upload_bytes(path, data, mime)
    try:
        syllabus_version = SyllabusVersion(
            academic_scheme_id=scheme.id,
            subject_id=subject.id,
            version=version_label,
            verification_status=publication,
            active=True,
        )
        db.add(syllabus_version)
        db.flush()
        document = SyllabusDocument(
            syllabus_version_id=syllabus_version.id,
            original_filename=safe_original_filename(file.filename),
            title=clean_title,
            description=clean_description,
            storage_path=path,
            file_type=extension,
            file_size=len(data),
            verification_status=publication,
            active=True,
        )
        db.add(document)
        db.commit()
        db.refresh(syllabus_version)
        db.refresh(document)
    except IntegrityError as exc:
        db.rollback()
        _cleanup(path)
        raise HTTPException(status_code=409, detail="This syllabus version already exists for the subject") from exc
    except Exception:
        db.rollback()
        _cleanup(path)
        raise
    return _syllabus_payload(syllabus_version, document, subject)


@router.patch("/api/v1/admin/syllabus/{document_id}")
def admin_update_syllabus(
    document_id: uuid.UUID,
    payload: SyllabusUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    document = db.get(SyllabusDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Syllabus document not found")
    version = db.get(SyllabusVersion, document.syllabus_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Syllabus version not found")
    previous_status = document.verification_status
    data = payload.model_dump(exclude_unset=True)
    if "subject_id" in data and data["subject_id"] is not None:
        new_subject = _subject_or_400(db, uuid.UUID(str(data["subject_id"])))
        version.subject_id = new_subject.id
        version.academic_scheme_id = new_subject.academic_scheme_id
    if "title" in data:
        document.title = clean_text(data["title"], field="Title", max_length=300)
    if "description" in data:
        document.description = clean_text(data["description"], field="Description", max_length=4000)
    if "status" in data and data["status"] is not None:
        publication = _status(str(data["status"]))
        document.verification_status = publication
        version.verification_status = publication
        if publication == VerificationStatus.VERIFIED and previous_status != VerificationStatus.VERIFIED:
            document.active = True
            version.active = True
    if "active" in data and data["active"] is not None:
        document.active = bool(data["active"])
        version.active = bool(data["active"])
    db.commit()
    db.refresh(document)
    subject = db.get(Subject, version.subject_id)
    return _syllabus_payload(version, document, subject)


def admin_archive_syllabus(
    document_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    document = db.get(SyllabusDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Syllabus document not found")
    version = db.get(SyllabusVersion, document.syllabus_version_id)
    document.active = False
    if version is not None:
        version.active = False
    db.commit()
    return {"message": "Syllabus document archived"}


@router.delete("/api/v1/admin/syllabus/{document_id}")
def admin_archive_or_delete_syllabus(
    document_id: uuid.UUID,
    permanent: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if permanent:
        return _delete_syllabus_core(db, document_id)
    return admin_archive_syllabus(document_id, admin, db)


@router.delete("/api/v1/admin/syllabus/{document_id}/permanent")
def admin_delete_syllabus(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _delete_syllabus_core(db, document_id)


# ----------------------------------------------------------------- admin PYQs
@router.get("/api/v1/admin/pyqs")
def admin_list_pyqs(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
    exam_type: str | None = None,
    year: int | None = None,
):
    statement = select(QuestionPaper, UploadedDocument).join(
        UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id
    )
    if subject_id:
        statement = statement.where(QuestionPaper.subject_id == subject_id)
    if exam_type and exam_type.upper() in {item.value for item in ExamType}:
        statement = statement.where(QuestionPaper.exam_type == ExamType(exam_type.upper()))
    if year:
        statement = statement.where(QuestionPaper.examination_year == year)
    rows = db.execute(
        statement.order_by(QuestionPaper.examination_year.desc().nullslast(), QuestionPaper.id)
    ).all()
    subjects = _subjects_map(db, {paper.subject_id for paper, _ in rows})
    items = []
    for paper, document in rows:
        subject = subjects.get(paper.subject_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{subject.code if subject else ''} {subject.name if subject else ''} "
                f"{paper.title or ''} {document.original_filename}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_pyq_payload(paper, document, subject))
    return {"items": items, "total": len(items)}


@router.post("/api/v1/admin/pyqs", status_code=201)
async def admin_upload_pyq(
    file: UploadFile = File(...),
    subject_id: uuid.UUID = Form(...),
    exam_type: str = Form(...),
    examination_year: int = Form(...),
    cie_number: int | None = Form(default=None),
    title: str | None = Form(default=None),
    description: str | None = Form(default=None),
    status: str = Form(default="DRAFT"),
    background_tasks: BackgroundTasks = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subject = _subject_or_400(db, subject_id)
    scheme, semester = _subject_context(db, subject)
    normalized_exam = (exam_type or "").strip().upper()
    if normalized_exam not in {item.value for item in ExamType}:
        raise HTTPException(status_code=422, detail="Exam type must be CIE or SEE")
    if examination_year < 2000 or examination_year > 2100:
        raise HTTPException(status_code=422, detail="Examination year is out of range")
    if normalized_exam == "CIE" and cie_number is not None and (cie_number < 1 or cie_number > 3):
        raise HTTPException(status_code=422, detail="CIE number must be between 1 and 3")
    publication = _status(status)
    clean_title = clean_text(title, field="Title", max_length=300)
    clean_description = clean_text(description, field="Description", max_length=4000)

    data = await _read_upload(file)
    extension, mime = validate_file(
        category="pyq", filename=file.filename, content_type=file.content_type, size=len(data)
    )
    content_sha256 = hashlib.sha256(data).hexdigest()
    duplicate = _active_pyq_with_hash(db, content_sha256)
    try:
        legacy_duplicate = _matches_legacy_pyq(db, len(data), content_sha256)
    except HTTPException:
        db.rollback()
        raise
    if duplicate or legacy_duplicate:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An active question paper with identical PDF content already exists",
        )

    path = safe_object_path("pyq", scheme_id=scheme.id, subject_id=subject.id, extension=extension)
    try:
        storage.upload_bytes(path, data, mime)
        document = UploadedDocument(
            original_filename=safe_original_filename(file.filename),
            title=clean_title,
            description=clean_description,
            file_type=extension,
            file_size=len(data),
            storage_path=path,
            content_sha256=content_sha256,
            subject_id=subject.id,
            academic_scheme_id=scheme.id,
            semester_id=semester.id,
            exam_type=ExamType(normalized_exam),
            cie_number=cie_number,
            examination_year=examination_year,
            uploaded_by=admin.id,
            permission_status=(
                PermissionStatus.APPROVED if publication == VerificationStatus.VERIFIED else PermissionStatus.PENDING
            ),
            verification_status=publication,
            active=True,
        )
        db.add(document)
        db.flush()
        paper = QuestionPaper(
            uploaded_document_id=document.id,
            title=clean_title,
            description=clean_description,
            subject_id=subject.id,
            academic_scheme_id=scheme.id,
            semester_id=semester.id,
            exam_type=ExamType(normalized_exam),
            cie_number=cie_number,
            examination_year=examination_year,
        )
        db.add(paper)
        db.commit()
        db.refresh(document)
        db.refresh(paper)

        # Trigger background automated AI analysis job
        try:
            analysis_job = AnalysisJob(
                question_paper_id=paper.id,
                uploaded_document_id=document.id,
                status=AnalysisJobStatus.PENDING,
                stage="Queued for automated AI analysis",
                progress_percent=0,
            )
            db.add(analysis_job)
            db.commit()
            db.refresh(analysis_job)

            if background_tasks is not None:
                background_tasks.add_task(run_pyq_analysis_job, analysis_job.id)
        except Exception as job_exc:
            logger.warning("Could not initiate background analysis job: %s", job_exc)
    except IntegrityError as exc:
        db.rollback()
        _cleanup(path)
        if _is_active_pyq_hash_conflict(exc):
            raise HTTPException(
                status_code=409,
                detail="An active question paper with identical PDF content already exists",
            ) from exc
        raise
    except Exception:
        db.rollback()
        _cleanup(path)
        raise
    return _pyq_payload(paper, document, subject)


@router.patch("/api/v1/admin/pyqs/{paper_id}")
def admin_update_pyq(
    paper_id: uuid.UUID,
    payload: PyqUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    paper = db.get(QuestionPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Question paper not found")
    document = db.get(UploadedDocument, paper.uploaded_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Question paper file record not found")
    previous_status = document.verification_status
    data = payload.model_dump(exclude_unset=True)
    publication = (
        _status(str(data["status"]))
        if "status" in data and data["status"] is not None
        else None
    )
    is_reactivating = data.get("active") is True or (
        publication == VerificationStatus.VERIFIED
        and previous_status != VerificationStatus.VERIFIED
    )
    if not document.active and is_reactivating:
        content_sha256 = document.content_sha256
        if content_sha256 is None:
            try:
                existing_data = storage.download_bytes(document.storage_path)
            except storage.StorageError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="The archived question paper could not be verified. Please retry later.",
                ) from exc
            content_sha256 = hashlib.sha256(existing_data).hexdigest()
        duplicate = _active_pyq_with_hash(
            db, content_sha256, exclude_paper_id=paper.id
        )
        try:
            legacy_duplicate = _matches_legacy_pyq(db, document.file_size, content_sha256)
        except HTTPException:
            db.rollback()
            raise
        if duplicate or legacy_duplicate:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="An active question paper with identical PDF content already exists",
            )
    if "subject_id" in data and data["subject_id"] is not None:
        new_subject = _subject_or_400(db, uuid.UUID(str(data["subject_id"])))
        paper.subject_id = new_subject.id
        if document is not None:
            document.academic_scheme_id = new_subject.academic_scheme_id
            document.semester_id = new_subject.semester_id
    if "title" in data:
        paper.title = clean_text(data["title"], field="Title", max_length=300)
        document.title = paper.title
    if "description" in data:
        paper.description = clean_text(data["description"], field="Description", max_length=4000)
        document.description = paper.description
    if publication is not None:
        document.verification_status = publication
        document.permission_status = (
            PermissionStatus.APPROVED if publication == VerificationStatus.VERIFIED else PermissionStatus.PENDING
        )
        if publication == VerificationStatus.VERIFIED and previous_status != VerificationStatus.VERIFIED:
            document.active = True
    if "active" in data and data["active"] is not None:
        document.active = bool(data["active"])
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_active_pyq_hash_conflict(exc):
            raise HTTPException(
                status_code=409,
                detail="An active question paper with identical PDF content already exists",
            ) from exc
        raise
    db.refresh(paper)
    db.refresh(document)
    return _pyq_payload(paper, document, db.get(Subject, paper.subject_id))


def admin_archive_pyq(
    paper_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    paper = db.get(QuestionPaper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Question paper not found")
    document = db.get(UploadedDocument, paper.uploaded_document_id)
    if document is not None:
        document.active = False
    db.commit()
    return {"message": "Question paper archived"}


@router.delete("/api/v1/admin/pyqs/{paper_id}")
def admin_archive_or_delete_pyq(
    paper_id: uuid.UUID,
    permanent: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if permanent:
        return _delete_pyq_core(db, paper_id)
    return admin_archive_pyq(paper_id, admin, db)


@router.delete("/api/v1/admin/pyqs/{paper_id}/permanent")
def admin_delete_pyq(
    paper_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _delete_pyq_core(db, paper_id)


# ------------------------------------------------------------ admin resources
@router.get("/api/v1/admin/resources")
def admin_list_resources(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
    resource_type: str | None = None,
):
    statement = select(LearningResource)
    if subject_id:
        statement = statement.where(LearningResource.subject_id == subject_id)
    if resource_type and resource_type.upper() in RESOURCE_TYPES:
        statement = statement.where(LearningResource.resource_type == resource_type.upper())
    rows = db.scalars(statement.order_by(LearningResource.uploaded_at.desc())).all()
    subjects = _subjects_map(db, {row.subject_id for row in rows})
    units = _units_map(db, {row.unit_id for row in rows if row.unit_id is not None})
    items = []
    for row in rows:
        subject = subjects.get(row.subject_id)
        unit = units.get(row.unit_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{row.title} {row.description or ''} {getattr(row, 'link_title', '') or ''} "
                f"{getattr(row, 'external_url', '') or ''} {subject.code if subject else ''} "
                f"{subject.name if subject else ''}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_resource_payload(row, subject, unit))
    return {"items": items, "total": len(items)}


@router.get("/api/v1/admin/subjects/{subject_id}/units")
def admin_list_subject_units(
    subject_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    units = db.scalars(
        select(Unit)
        .where(Unit.subject_id == subject.id, Unit.active.is_(True))
        .order_by(Unit.order_index)
    ).all()
    return [{"id": str(u.id), "title": u.title, "order_index": u.order_index} for u in units]


@router.post("/api/v1/admin/resources", status_code=201)
async def admin_upload_resource(
    file: UploadFile | None = File(default=None),
    subject_id: uuid.UUID = Form(...),
    resource_type: str = Form(...),
    title: str = Form(...),
    resource_source: str = Form(default="FILE"),
    external_url: str | None = Form(default=None),
    link_title: str | None = Form(default=None),
    unit_id: uuid.UUID | None = Form(default=None),
    description: str | None = Form(default=None),
    status: str = Form(default="DRAFT"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subject = _subject_or_400(db, subject_id)
    scheme, semester = _subject_context(db, subject)
    normalized_type = (resource_type or "").strip().upper()
    if normalized_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Invalid resource type")

    raw_source = str(resource_source) if isinstance(resource_source, str) else "FILE"
    normalized_source = raw_source.strip().upper()
    if normalized_source not in {"FILE", "LINK", "BOTH"}:
        raise HTTPException(status_code=422, detail="Resource source must be FILE, LINK, or BOTH")

    raw_status = str(status) if isinstance(status, str) else "DRAFT"
    publication = _status(raw_status)
    clean_title = clean_text(title, field="Title", max_length=300, required=True)
    raw_desc = str(description) if isinstance(description, str) else None
    clean_description = clean_text(raw_desc, field="Description", max_length=4000)
    raw_link_title = str(link_title) if isinstance(link_title, str) else None
    clean_link_title = clean_text(raw_link_title, field="Link title", max_length=300)

    unit = None
    raw_unit_id = unit_id if isinstance(unit_id, uuid.UUID) else None
    if raw_unit_id is not None:
        unit = db.get(Unit, raw_unit_id)
        if unit is None or unit.subject_id != subject.id:
            raise HTTPException(status_code=400, detail="Selected unit does not belong to this subject")

    clean_url = None
    raw_ext_url = str(external_url) if isinstance(external_url, str) else None
    if normalized_source in {"LINK", "BOTH"}:
        clean_url = validate_external_url(raw_ext_url, required=True)
    elif raw_ext_url:
        clean_url = validate_external_url(raw_ext_url, required=False)

    has_file = file is not None and bool(file.filename and file.filename.strip())
    if normalized_source in {"FILE", "BOTH"} and not has_file:
        raise HTTPException(status_code=422, detail=f"A valid file is required when source is {normalized_source.capitalize()}")

    path = None
    extension = None
    file_size = None
    orig_name = None

    if has_file and file is not None:
        data = await _read_upload(file)
        extension, mime = validate_file(
            category="resource", filename=file.filename, content_type=file.content_type, size=len(data)
        )
        file_size = len(data)
        orig_name = safe_original_filename(file.filename)
        path = safe_object_path("resource", scheme_id=scheme.id, subject_id=subject.id, extension=extension)
        storage.upload_bytes(path, data, mime)

    try:
        resource = LearningResource(
            title=clean_title,
            description=clean_description,
            subject_id=subject.id,
            academic_scheme_id=scheme.id,
            semester_id=semester.id,
            unit_id=unit.id if unit else None,
            resource_type=normalized_type,
            resource_source=normalized_source,
            external_url=clean_url,
            link_title=clean_link_title,
            storage_path=path,
            original_filename=orig_name,
            file_type=extension,
            file_size=file_size,
            uploaded_by=admin.id,
            verification_status=publication,
            active=True,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
    except Exception:
        db.rollback()
        if path:
            _cleanup(path)
        raise
    return _resource_payload(resource, subject, unit)


@router.patch("/api/v1/admin/resources/{resource_id}")
def admin_update_resource(
    resource_id: uuid.UUID,
    payload: ResourceUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resource = db.get(LearningResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Learning resource not found")
    previous_status = resource.verification_status
    data = payload.model_dump(exclude_unset=True)
    if "subject_id" in data and data["subject_id"] is not None:
        new_subject = _subject_or_400(db, uuid.UUID(str(data["subject_id"])))
        resource.subject_id = new_subject.id
        resource.academic_scheme_id = new_subject.academic_scheme_id
        resource.semester_id = new_subject.semester_id
        if resource.unit_id:
            unit = db.get(Unit, resource.unit_id)
            if unit is None or unit.subject_id != new_subject.id:
                resource.unit_id = None
    if "title" in data:
        resource.title = clean_text(data["title"], field="Title", max_length=300, required=True)
    if "description" in data:
        resource.description = clean_text(data["description"], field="Description", max_length=4000)
    if "resource_type" in data and data["resource_type"] is not None:
        normalized_type = str(data["resource_type"]).upper()
        if normalized_type not in RESOURCE_TYPES:
            raise HTTPException(status_code=422, detail="Invalid resource type")
        resource.resource_type = normalized_type
    if "external_url" in data:
        resource.external_url = validate_external_url(data["external_url"], required=False)
    if "link_title" in data:
        resource.link_title = clean_text(data["link_title"], field="Link title", max_length=300)
    if "resource_source" in data and data["resource_source"] is not None:
        norm_source = str(data["resource_source"]).upper()
        if norm_source in {"FILE", "LINK", "BOTH"}:
            resource.resource_source = norm_source
    if "unit_id" in data:
        if data["unit_id"]:
            unit = db.get(Unit, uuid.UUID(str(data["unit_id"])))
            if unit and unit.subject_id == resource.subject_id:
                resource.unit_id = unit.id
        else:
            resource.unit_id = None
    if "status" in data and data["status"] is not None:
        publication = _status(str(data["status"]))
        resource.verification_status = publication
        if publication == VerificationStatus.VERIFIED and previous_status != VerificationStatus.VERIFIED:
            resource.active = True
    if "active" in data and data["active"] is not None:
        resource.active = bool(data["active"])
    resource.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(resource)
    res_unit_id = getattr(resource, "unit_id", None)
    unit = db.get(Unit, res_unit_id) if res_unit_id else None
    return _resource_payload(resource, db.get(Subject, resource.subject_id), unit)


def admin_archive_resource(
    resource_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    resource = db.get(LearningResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Learning resource not found")
    resource.active = False
    db.commit()
    return {"message": "Learning resource archived"}


@router.delete("/api/v1/admin/resources/{resource_id}")
def admin_archive_or_delete_resource(
    resource_id: uuid.UUID,
    permanent: bool = False,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if permanent:
        return _delete_resource_core(db, resource_id)
    return admin_archive_resource(resource_id, admin, db)


@router.delete("/api/v1/admin/resources/{resource_id}/permanent")
def admin_delete_resource(
    resource_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _delete_resource_core(db, resource_id)


@router.delete("/api/v1/admin/documents/{document_id}")
def admin_delete_uploaded_document(
    document_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _delete_document_core(db, document_id)


@router.delete("/api/v1/admin/content/{kind}/{content_id}")
def admin_delete_content(
    kind: str,
    content_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    k = kind.lower().strip()
    if k in ("pyq", "pyqs"):
        return _delete_pyq_core(db, content_id)
    if k in ("syllabus", "syllabi"):
        return _delete_syllabus_core(db, content_id)
    if k in ("resource", "resources"):
        return _delete_resource_core(db, content_id)
    if k in ("document", "documents"):
        return _delete_document_core(db, content_id)
    raise HTTPException(status_code=400, detail=f"Unsupported content kind: {kind}")


# --------------------------------------------------------------- uploads hub
@router.get("/api/v1/admin/uploads")
def admin_uploads(
    admin: User = Depends(require_admin), db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)
):
    syllabus_rows = db.execute(
        select(SyllabusVersion, SyllabusDocument)
        .join(SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id)
        .order_by(SyllabusVersion.created_at.desc())
        .limit(limit)
    ).all()
    pyq_rows = db.execute(
        select(QuestionPaper, UploadedDocument)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .order_by(UploadedDocument.uploaded_at.desc())
        .limit(limit)
    ).all()
    resources = db.scalars(
        select(LearningResource).order_by(LearningResource.uploaded_at.desc()).limit(limit)
    ).all()
    subject_ids = {version.subject_id for version, _ in syllabus_rows}
    subject_ids |= {paper.subject_id for paper, _ in pyq_rows}
    subject_ids |= {resource.subject_id for resource in resources}
    subjects = _subjects_map(db, subject_ids)

    items: list[dict] = []
    for version, document in syllabus_rows:
        items.append(
            {
                "kind": "SYLLABUS",
                "id": str(document.id),
                "title": document.title or document.original_filename,
                "subject_code": subjects[version.subject_id].code if version.subject_id in subjects else None,
                "status": document.verification_status.value,
                "active": document.active,
                "created_at": _iso(version.created_at),
                "size": document.file_size,
                "file_type": getattr(document, "file_type", None),
            }
        )
    for paper, document in pyq_rows:
        items.append(
            {
                "kind": "PYQ",
                "id": str(paper.id),
                "title": paper.title or document.original_filename,
                "subject_code": subjects[paper.subject_id].code if paper.subject_id in subjects else None,
                "status": document.verification_status.value,
                "active": document.active,
                "created_at": _iso(document.uploaded_at),
                "size": document.file_size,
                "file_type": getattr(document, "file_type", None),
            }
        )
    for resource in resources:
        items.append(
            {
                "kind": "RESOURCE",
                "id": str(resource.id),
                "title": resource.title,
                "subject_code": subjects[resource.subject_id].code if resource.subject_id in subjects else None,
                "status": resource.verification_status.value,
                "active": resource.active,
                "created_at": _iso(resource.uploaded_at),
                "size": resource.file_size,
                "file_type": getattr(resource, "file_type", None),
            }
        )
    items.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {"items": items[:limit], "total": len(items)}


# ----------------------------------------------------------- student content
def _student_profile(db: Session, user: User) -> StudentProfile:
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if profile is None:
        raise HTTPException(status_code=409, detail="Student onboarding is required")
    return profile


def _enrolled_subject_ids(db: Session, profile: StudentProfile) -> set[uuid.UUID]:
    rows = db.scalars(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.active.is_(True),
        )
    ).all()
    enrolled_ids = {
        row.subject_id if hasattr(row, "subject_id") else row
        for row in rows
    }
    academic_scheme_id = getattr(profile, "academic_scheme_id", None)
    current_semester_id = getattr(profile, "current_semester_id", None)
    branch_id = getattr(profile, "branch_id", None)

    if academic_scheme_id and current_semester_id:
        try:
            core_stmt = select(Subject).where(
                Subject.academic_scheme_id == academic_scheme_id,
                Subject.semester_id == current_semester_id,
                Subject.subject_type == "CORE",
                Subject.active.is_(True),
            )
            if branch_id:
                offered_count = (
                    db.scalar(
                        select(func.count(BranchSubjectOffering.subject_id)).where(
                            BranchSubjectOffering.branch_id == branch_id,
                            BranchSubjectOffering.active.is_(True),
                        )
                    )
                    or 0
                )
                if offered_count > 0:
                    core_stmt = core_stmt.where(
                        Subject.id.in_(
                            select(BranchSubjectOffering.subject_id).where(
                                BranchSubjectOffering.branch_id == branch_id,
                                BranchSubjectOffering.active.is_(True),
                            )
                        )
                    )
            core_subjects = db.scalars(core_stmt).all()
            for s in core_subjects:
                s_id = s.id if hasattr(s, "id") else s
                enrolled_ids.add(s_id)
        except Exception:
            pass
    return enrolled_ids


def _require_enrolled(subject_ids: set[uuid.UUID], subject_id: uuid.UUID) -> None:
    if subject_id not in subject_ids:
        raise HTTPException(status_code=403, detail="This content is not available for your enrollment")


@router.get("/api/v1/student/syllabus")
def student_list_syllabus(
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
):
    profile = _student_profile(db, student)
    subject_ids = _enrolled_subject_ids(db, profile)
    if not subject_ids:
        return {"items": [], "total": 0}
    statement = (
        select(SyllabusVersion, SyllabusDocument)
        .join(SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id)
        .where(
            SyllabusVersion.subject_id.in_(subject_ids),
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusDocument.active.is_(True),
            SyllabusDocument.verification_status == VerificationStatus.VERIFIED,
        )
    )
    academic_scheme_id = getattr(profile, "academic_scheme_id", None)
    if academic_scheme_id:
        statement = statement.where(
            or_(
                SyllabusVersion.academic_scheme_id.is_(None),
                SyllabusVersion.academic_scheme_id == academic_scheme_id,
            )
        )
    if subject_id:
        _require_enrolled(subject_ids, subject_id)
        statement = statement.where(SyllabusVersion.subject_id == subject_id)
    rows = db.execute(statement.order_by(SyllabusVersion.subject_id, SyllabusVersion.version)).all()
    subjects = _subjects_map(db, {version.subject_id for version, _ in rows})
    items = []
    for version, document in rows:
        subject = subjects.get(version.subject_id)
        if subject is None:
            continue
        if search:
            needle = search.strip().lower()
            if needle not in f"{subject.code} {subject.name} {document.original_filename}".lower():
                continue
        items.append(_syllabus_payload(version, document, subject))
    return {"items": items, "total": len(items)}


@router.get("/api/v1/student/pyqs")
def student_list_pyqs(
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
    year: int | None = None,
    exam_type: str | None = None,
):
    profile = _student_profile(db, student)
    subject_ids = _enrolled_subject_ids(db, profile)
    if not subject_ids:
        return {"items": [], "total": 0}
    statement = (
        select(QuestionPaper, UploadedDocument)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            QuestionPaper.subject_id.in_(subject_ids),
            UploadedDocument.active.is_(True),
            UploadedDocument.verification_status == VerificationStatus.VERIFIED,
            UploadedDocument.permission_status == PermissionStatus.APPROVED,
        )
    )
    academic_scheme_id = getattr(profile, "academic_scheme_id", None)
    current_semester_id = getattr(profile, "current_semester_id", None)
    if academic_scheme_id:
        statement = statement.where(
            or_(
                UploadedDocument.academic_scheme_id.is_(None),
                UploadedDocument.academic_scheme_id == academic_scheme_id,
            )
        )
    if current_semester_id:
        statement = statement.where(
            or_(
                UploadedDocument.semester_id.is_(None),
                UploadedDocument.semester_id == current_semester_id,
            )
        )
    if subject_id:
        _require_enrolled(subject_ids, subject_id)
        statement = statement.where(QuestionPaper.subject_id == subject_id)
    if year:
        statement = statement.where(QuestionPaper.examination_year == year)
    if exam_type and exam_type.upper() in {item.value for item in ExamType}:
        statement = statement.where(QuestionPaper.exam_type == ExamType(exam_type.upper()))
    rows = db.execute(
        statement.order_by(QuestionPaper.examination_year.desc().nullslast(), QuestionPaper.exam_type)
    ).all()
    subjects = _subjects_map(db, {paper.subject_id for paper, _ in rows})
    items = []
    for paper, document in rows:
        subject = subjects.get(paper.subject_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{subject.code if subject else ''} {subject.name if subject else ''} "
                f"{paper.title or ''} {document.original_filename}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_pyq_payload(paper, document, subject))
    return {"items": items, "total": len(items)}


@router.get("/api/v1/student/resources")
def student_list_resources(
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
    search: str | None = None,
    subject_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_source: str | None = None,
):
    profile = _student_profile(db, student)
    subject_ids = _enrolled_subject_ids(db, profile)
    if not subject_ids:
        return {"items": [], "total": 0}
    statement = select(LearningResource).where(
        LearningResource.subject_id.in_(subject_ids),
        LearningResource.active.is_(True),
        LearningResource.verification_status == VerificationStatus.VERIFIED,
    )
    academic_scheme_id = getattr(profile, "academic_scheme_id", None)
    current_semester_id = getattr(profile, "current_semester_id", None)
    if academic_scheme_id:
        statement = statement.where(
            or_(
                LearningResource.academic_scheme_id.is_(None),
                LearningResource.academic_scheme_id == academic_scheme_id,
            )
        )
    if current_semester_id:
        statement = statement.where(
            or_(
                LearningResource.semester_id.is_(None),
                LearningResource.semester_id == current_semester_id,
            )
        )
    if subject_id:
        _require_enrolled(subject_ids, subject_id)
        statement = statement.where(LearningResource.subject_id == subject_id)
    if unit_id:
        statement = statement.where(LearningResource.unit_id == unit_id)
    if resource_type and resource_type.upper() in RESOURCE_TYPES:
        statement = statement.where(LearningResource.resource_type == resource_type.upper())
    if resource_source and resource_source.upper() in {"FILE", "LINK", "BOTH"}:
        statement = statement.where(LearningResource.resource_source == resource_source.upper())
    rows = db.scalars(statement.order_by(LearningResource.uploaded_at.desc())).all()
    subjects = _subjects_map(db, {row.subject_id for row in rows})
    units = _units_map(db, {row.unit_id for row in rows if row.unit_id is not None})
    items = []
    for row in rows:
        subject = subjects.get(row.subject_id)
        unit = units.get(row.unit_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{row.title} {row.description or ''} {getattr(row, 'link_title', '') or ''} "
                f"{getattr(row, 'external_url', '') or ''} {subject.code if subject else ''} "
                f"{subject.name if subject else ''}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_resource_payload(row, subject, unit))
    return {"items": items, "total": len(items)}


@router.get("/api/v1/student/subjects/{subject_id}")
def student_subject_detail(
    subject_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = _student_profile(db, student)
    subject_ids = _enrolled_subject_ids(db, profile)
    _require_enrolled(subject_ids, subject_id)
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.active:
        raise HTTPException(status_code=404, detail="Subject not found")
    scheme, semester = _subject_context(db, subject)

    syllabus_rows = db.execute(
        select(SyllabusVersion, SyllabusDocument)
        .join(SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id)
        .where(
            SyllabusVersion.subject_id == subject.id,
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusDocument.active.is_(True),
            SyllabusDocument.verification_status == VerificationStatus.VERIFIED,
        )
        .order_by(SyllabusVersion.version)
    ).all()
    pyq_rows = db.execute(
        select(QuestionPaper, UploadedDocument)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            QuestionPaper.subject_id == subject.id,
            UploadedDocument.active.is_(True),
            UploadedDocument.verification_status == VerificationStatus.VERIFIED,
            UploadedDocument.permission_status == PermissionStatus.APPROVED,
        )
        .order_by(QuestionPaper.examination_year.desc().nullslast())
    ).all()
    resource_rows = db.scalars(
        select(LearningResource).where(
            LearningResource.subject_id == subject.id,
            LearningResource.active.is_(True),
            LearningResource.verification_status == VerificationStatus.VERIFIED,
        )
    ).all()
    return {
        "subject": {
            "id": str(subject.id),
            "code": subject.code,
            "name": subject.name,
            "subject_type": subject.subject_type,
            "credits": subject.credits,
            "description": subject.description,
            "semester": semester.name,
            "semester_number": semester.number,
            "academic_scheme": scheme.name,
        },
        "syllabus": [_syllabus_payload(version, document, subject) for version, document in syllabus_rows],
        "pyqs": [_pyq_payload(paper, document, subject) for paper, document in pyq_rows],
        "resources": [_resource_payload(resource, subject) for resource in resource_rows],
    }


# --------------------------------------------------------------- downloads
def _signed_download(
    path: str,
    filename: str | None,
    *,
    preview: bool = False,
    file_type: str | None = None,
) -> dict:
    if preview and (file_type or "").lower() != "pdf":
        raise HTTPException(
            status_code=415,
            detail="Preview is only available for PDF documents. Download the file instead.",
        )
    try:
        if preview:
            # No download option: Supabase serves the object inline so the
            # browser's native PDF viewer can render it in a new tab.
            url = storage.create_signed_url(path)
        else:
            url = storage.create_signed_url(path, download_filename=filename)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Private storage is unavailable") from exc
    return {
        "url": url,
        "expires_in": storage.SIGNED_URL_TTL_SECONDS,
        "filename": filename,
        "disposition": "inline" if preview else "attachment",
    }


@router.get("/api/v1/student/{kind}/{content_id}/download")
def student_download(
    kind: str,
    content_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
    preview: bool = False,
):
    profile = _student_profile(db, student)
    subject_ids = _enrolled_subject_ids(db, profile)
    if kind == "syllabus":
        document = db.get(SyllabusDocument, content_id)
        version = db.get(SyllabusVersion, document.syllabus_version_id) if document else None
        if (
            document is None
            or version is None
            or not document.active
            or not version.active
            or document.verification_status != VerificationStatus.VERIFIED
            or version.verification_status != VerificationStatus.VERIFIED
        ):
            raise HTTPException(status_code=404, detail="Syllabus document not found")
        _require_enrolled(subject_ids, version.subject_id)
        return _signed_download(
            document.storage_path,
            document.original_filename,
            preview=preview,
            file_type=getattr(document, "file_type", None),
        )
    if kind == "pyq":
        paper = db.get(QuestionPaper, content_id)
        document = db.get(UploadedDocument, paper.uploaded_document_id) if paper else None
        if (
            paper is None
            or document is None
            or not document.active
            or document.verification_status != VerificationStatus.VERIFIED
            or document.permission_status != PermissionStatus.APPROVED
        ):
            raise HTTPException(status_code=404, detail="Question paper not found")
        _require_enrolled(subject_ids, paper.subject_id)
        return _signed_download(
            document.storage_path,
            document.original_filename,
            preview=preview,
            file_type=getattr(document, "file_type", None),
        )
    if kind == "resource":
        resource = db.get(LearningResource, content_id)
        if (
            resource is None
            or not resource.active
            or resource.verification_status != VerificationStatus.VERIFIED
        ):
            raise HTTPException(status_code=404, detail="Learning resource not found")
        _require_enrolled(subject_ids, resource.subject_id)
        if not resource.storage_path:
            raise HTTPException(
                status_code=400,
                detail="This resource is an external link and has no downloadable file",
            )
        return _signed_download(
            resource.storage_path,
            resource.original_filename,
            preview=preview,
            file_type=getattr(resource, "file_type", None),
        )
    raise HTTPException(status_code=404, detail="Unknown content kind")


@router.get("/api/v1/admin/{kind}/{content_id}/download")
def admin_download(
    kind: str,
    content_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    preview: bool = False,
):
    if kind == "syllabus":
        document = db.get(SyllabusDocument, content_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Syllabus document not found")
        return _signed_download(
            document.storage_path,
            document.original_filename,
            preview=preview,
            file_type=getattr(document, "file_type", None),
        )
    if kind == "pyq":
        paper = db.get(QuestionPaper, content_id)
        document = db.get(UploadedDocument, paper.uploaded_document_id) if paper else None
        if document is None:
            raise HTTPException(status_code=404, detail="Question paper not found")
        return _signed_download(
            document.storage_path,
            document.original_filename,
            preview=preview,
            file_type=getattr(document, "file_type", None),
        )
    if kind == "resource":
        resource = db.get(LearningResource, content_id)
        if resource is None:
            raise HTTPException(status_code=404, detail="Learning resource not found")
        if not resource.storage_path:
            raise HTTPException(
                status_code=400,
                detail="This resource is an external link and has no downloadable file",
            )
        return _signed_download(
            resource.storage_path,
            resource.original_filename,
            preview=preview,
            file_type=getattr(resource, "file_type", None),
        )
    raise HTTPException(status_code=404, detail="Unknown content kind")
