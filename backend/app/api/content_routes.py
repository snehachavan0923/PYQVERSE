from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_student
from app.database.connection import get_db
from app.models.academic import (
    AcademicScheme,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.document import ExamType, PermissionStatus, QuestionPaper, UploadedDocument
from app.models.resource import LearningResource, ResourceType
from app.models.syllabus import SyllabusDocument, SyllabusVersion, VerificationStatus
from app.models.user import User
from app.schemas.content import PyqUpdate, ResourceUpdate, SyllabusUpdate
from app.services import storage
from app.services.content import (
    MAX_FILE_BYTES,
    clean_text,
    safe_object_path,
    safe_original_filename,
    validate_file,
)

router = APIRouter(tags=["content"])

VALID_STATUSES = {status.value for status in VerificationStatus}
RESOURCE_TYPES = {item.value for item in ResourceType}


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


def _subject_context(db: Session, subject: Subject) -> tuple[AcademicScheme, Semester]:
    scheme = db.get(AcademicScheme, subject.academic_scheme_id)
    semester = db.get(Semester, subject.semester_id)
    if scheme is None or semester is None:
        raise HTTPException(status_code=400, detail="The subject academic context is incomplete")
    return scheme, semester


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


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


def _resource_payload(resource: LearningResource, subject: Subject | None) -> dict:
    return {
        "id": str(resource.id),
        "subject_id": str(resource.subject_id),
        "subject_code": subject.code if subject else None,
        "subject_name": subject.name if subject else None,
        "title": resource.title,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "original_filename": resource.original_filename,
        "file_type": resource.file_type,
        "file_size": resource.file_size,
        "verification_status": resource.verification_status.value,
        "active": resource.active,
        "uploaded_at": _iso(resource.uploaded_at),
        "uploaded_by": str(resource.uploaded_by),
    }


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
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        document.title = clean_text(data["title"], field="Title", max_length=300)
    if "description" in data:
        document.description = clean_text(data["description"], field="Description", max_length=4000)
    if "status" in data and data["status"] is not None:
        publication = _status(str(data["status"]))
        document.verification_status = publication
        version.verification_status = publication
    if "active" in data and data["active"] is not None:
        document.active = bool(data["active"])
        version.active = bool(data["active"])
    db.commit()
    db.refresh(document)
    subject = db.get(Subject, version.subject_id)
    return _syllabus_payload(version, document, subject)


@router.delete("/api/v1/admin/syllabus/{document_id}")
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

    duplicate = db.scalars(
        select(QuestionPaper)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            QuestionPaper.subject_id == subject.id,
            QuestionPaper.exam_type == ExamType(normalized_exam),
            QuestionPaper.examination_year == examination_year,
            QuestionPaper.cie_number == cie_number,
            UploadedDocument.active.is_(True),
        )
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="A matching question paper already exists")

    data = await _read_upload(file)
    extension, mime = validate_file(
        category="pyq", filename=file.filename, content_type=file.content_type, size=len(data)
    )
    path = safe_object_path("pyq", scheme_id=scheme.id, subject_id=subject.id, extension=extension)
    storage.upload_bytes(path, data, mime)
    try:
        document = UploadedDocument(
            original_filename=safe_original_filename(file.filename),
            title=clean_title,
            description=clean_description,
            file_type=extension,
            file_size=len(data),
            storage_path=path,
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
    except IntegrityError as exc:
        db.rollback()
        _cleanup(path)
        raise HTTPException(status_code=409, detail="This question paper conflicts with an existing record") from exc
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
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        paper.title = clean_text(data["title"], field="Title", max_length=300)
        document.title = paper.title
    if "description" in data:
        paper.description = clean_text(data["description"], field="Description", max_length=4000)
        document.description = paper.description
    if "status" in data and data["status"] is not None:
        publication = _status(str(data["status"]))
        document.verification_status = publication
        document.permission_status = (
            PermissionStatus.APPROVED if publication == VerificationStatus.VERIFIED else PermissionStatus.PENDING
        )
    if "active" in data and data["active"] is not None:
        document.active = bool(data["active"])
    db.commit()
    db.refresh(paper)
    db.refresh(document)
    return _pyq_payload(paper, document, db.get(Subject, paper.subject_id))


@router.delete("/api/v1/admin/pyqs/{paper_id}")
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
    items = []
    for row in rows:
        subject = subjects.get(row.subject_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{row.title} {row.description or ''} {subject.code if subject else ''} "
                f"{subject.name if subject else ''}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_resource_payload(row, subject))
    return {"items": items, "total": len(items)}


@router.post("/api/v1/admin/resources", status_code=201)
async def admin_upload_resource(
    file: UploadFile = File(...),
    subject_id: uuid.UUID = Form(...),
    resource_type: str = Form(...),
    title: str = Form(...),
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
    publication = _status(status)
    clean_title = clean_text(title, field="Title", max_length=300, required=True)
    clean_description = clean_text(description, field="Description", max_length=4000)

    data = await _read_upload(file)
    extension, mime = validate_file(
        category="resource", filename=file.filename, content_type=file.content_type, size=len(data)
    )
    path = safe_object_path("resource", scheme_id=scheme.id, subject_id=subject.id, extension=extension)
    storage.upload_bytes(path, data, mime)
    try:
        resource = LearningResource(
            title=clean_title,
            description=clean_description,
            subject_id=subject.id,
            academic_scheme_id=scheme.id,
            semester_id=semester.id,
            resource_type=normalized_type,
            storage_path=path,
            original_filename=safe_original_filename(file.filename),
            file_type=extension,
            file_size=len(data),
            uploaded_by=admin.id,
            verification_status=publication,
            active=True,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
    except Exception:
        db.rollback()
        _cleanup(path)
        raise
    return _resource_payload(resource, subject)


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
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        resource.title = clean_text(data["title"], field="Title", max_length=300, required=True)
    if "description" in data:
        resource.description = clean_text(data["description"], field="Description", max_length=4000)
    if "resource_type" in data and data["resource_type"] is not None:
        normalized_type = str(data["resource_type"]).upper()
        if normalized_type not in RESOURCE_TYPES:
            raise HTTPException(status_code=422, detail="Invalid resource type")
        resource.resource_type = normalized_type
    if "status" in data and data["status"] is not None:
        resource.verification_status = _status(str(data["status"]))
    if "active" in data and data["active"] is not None:
        resource.active = bool(data["active"])
    resource.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(resource)
    return _resource_payload(resource, db.get(Subject, resource.subject_id))


@router.delete("/api/v1/admin/resources/{resource_id}")
def admin_archive_resource(
    resource_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    resource = db.get(LearningResource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Learning resource not found")
    resource.active = False
    db.commit()
    return {"message": "Learning resource archived"}


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
    return {row.subject_id for row in rows}


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
    resource_type: str | None = None,
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
    if subject_id:
        _require_enrolled(subject_ids, subject_id)
        statement = statement.where(LearningResource.subject_id == subject_id)
    if resource_type and resource_type.upper() in RESOURCE_TYPES:
        statement = statement.where(LearningResource.resource_type == resource_type.upper())
    rows = db.scalars(statement.order_by(LearningResource.uploaded_at.desc())).all()
    subjects = _subjects_map(db, {row.subject_id for row in rows})
    items = []
    for row in rows:
        subject = subjects.get(row.subject_id)
        if search:
            needle = search.strip().lower()
            haystack = (
                f"{row.title} {row.description or ''} {subject.code if subject else ''} "
                f"{subject.name if subject else ''}"
            ).lower()
            if needle not in haystack:
                continue
        items.append(_resource_payload(row, subject))
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
        return _signed_download(
            resource.storage_path,
            resource.original_filename,
            preview=preview,
            file_type=getattr(resource, "file_type", None),
        )
    raise HTTPException(status_code=404, detail="Unknown content kind")
