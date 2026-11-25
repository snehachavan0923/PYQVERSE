import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.database.connection import get_db, test_database_connection
from app.models.academic import (
    AcademicScheme,
    Branch,
    BranchSubjectOffering,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.syllabus import Subtopic, SyllabusVersion, Topic, Unit, VerificationStatus
from app.models.user import User
from app.schemas.academic import (
    AcademicSchemeResponse,
    BranchResponse,
    SemesterResponse,
    SubjectResponse,
    UnitResponse,
    TopicResponse,
    SubtopicResponse,
)

router = APIRouter()


@router.get("/", tags=["root"])
def read_root() -> dict[str, str]:
    return {
        "message": "PYQVERSE API is running",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    try:
        test_database_connection()
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.get("/api/v1/academic/branches", response_model=list[BranchResponse])
def list_branches(db: Session = Depends(get_db)):
    return db.scalars(select(Branch).where(Branch.active.is_(True)).order_by(Branch.code)).all()


@router.get("/api/v1/academic/schemes", response_model=list[AcademicSchemeResponse])
def list_schemes(db: Session = Depends(get_db)):
    return db.scalars(
        select(AcademicScheme).where(AcademicScheme.active.is_(True)).order_by(AcademicScheme.code)
    ).all()


@router.get("/api/v1/academic/semesters", response_model=list[SemesterResponse])
def list_semesters(db: Session = Depends(get_db)):
    return db.scalars(select(Semester).where(Semester.active.is_(True)).order_by(Semester.number)).all()


@router.get("/api/v1/subjects", response_model=list[SubjectResponse])
def list_subjects(
    db: Session = Depends(get_db),
    branch_id: uuid.UUID | None = None,
    scheme_id: uuid.UUID | None = None,
    semester_id: uuid.UUID | None = None,
):
    statement = select(Subject).where(Subject.active.is_(True))
    branch = None
    scheme = None
    if branch_id:
        branch = db.get(Branch, branch_id)
        if branch is None or not branch.active:
            raise HTTPException(status_code=400, detail="Invalid branch")
        statement = statement.where(
            Subject.id.in_(
                select(BranchSubjectOffering.subject_id).where(
                    BranchSubjectOffering.branch_id == branch.id,
                    BranchSubjectOffering.active.is_(True),
                )
            )
        )
        statement = statement.where(
            or_(
                Subject.source_verification_status.is_(None),
                Subject.source_verification_status == "VERIFIED",
            )
        )
    if scheme_id:
        scheme = db.get(AcademicScheme, scheme_id)
        if scheme is None or not scheme.active:
            raise HTTPException(status_code=400, detail="Invalid academic scheme")
        if branch and scheme.college_id != branch.college_id:
            raise HTTPException(status_code=400, detail="Branch and scheme belong to different colleges")
        statement = statement.where(Subject.academic_scheme_id == scheme_id)
    if semester_id:
        semester = db.get(Semester, semester_id)
        if semester is None or not semester.active:
            raise HTTPException(status_code=400, detail="Invalid semester")
        if scheme and semester.academic_scheme_id != scheme.id:
            raise HTTPException(status_code=400, detail="Semester does not belong to the selected scheme")
        statement = statement.where(Subject.semester_id == semester_id)
    return db.scalars(statement.order_by(Subject.code)).all()


@router.get("/api/v1/subjects/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: str, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("/api/v1/subjects/{subject_id}/units", response_model=list[UnitResponse])
def list_units(
    subject_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    _require_student_subject_access(db, student, subject)
    return db.scalars(
        select(Unit)
        .join(SyllabusVersion, SyllabusVersion.id == Unit.syllabus_version_id)
        .where(
            Unit.subject_id == subject.id,
            Unit.active.is_(True),
            Unit.verification_status == VerificationStatus.VERIFIED,
            Unit.source_verification_status == "VERIFIED",
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusVersion.source_verification_status == "VERIFIED",
        )
        .order_by(Unit.order_index)
    ).all()


@router.get("/api/v1/units/{unit_id}/topics", response_model=list[TopicResponse])
def list_topics(
    unit_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    subject = db.get(Subject, unit.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    _require_student_subject_access(db, student, subject)
    _require_published_version(db, unit)
    return db.scalars(
        select(Topic).where(
            Topic.unit_id == unit.id,
            Topic.active.is_(True),
            Topic.verification_status == VerificationStatus.VERIFIED,
            Topic.source_verification_status == "VERIFIED",
        ).order_by(Topic.order_index)
    ).all()


@router.get(
    "/api/v1/topics/{topic_id}/subtopics",
    response_model=list[SubtopicResponse],
)
def list_subtopics(
    topic_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    unit = db.get(Unit, topic.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unit not found")
    subject = db.get(Subject, unit.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    _require_student_subject_access(db, student, subject)
    _require_published_version(db, unit)
    if (
        not topic.active
        or topic.verification_status != VerificationStatus.VERIFIED
        or topic.source_verification_status != "VERIFIED"
    ):
        raise HTTPException(status_code=404, detail="Topic not found")
    return db.scalars(
        select(Subtopic)
        .where(
            Subtopic.topic_id == topic.id,
            Subtopic.active.is_(True),
            Subtopic.verification_status == VerificationStatus.VERIFIED,
            Subtopic.source_verification_status == "VERIFIED",
        )
        .order_by(Subtopic.order_index)
    ).all()


def _require_student_subject_access(db: Session, student: User, subject: Subject) -> None:
    profile = db.scalars(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    ).first()
    if profile is None:
        raise HTTPException(status_code=409, detail="Student onboarding is required")
    if (
        not subject.active
        or not profile.profile_completed
        or profile.branch_id is None
        or profile.academic_scheme_id != subject.academic_scheme_id
        or profile.current_semester_id != subject.semester_id
    ):
        raise HTTPException(status_code=403, detail="This content is not available for your enrollment")
    enrollment = db.scalars(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.subject_id == subject.id,
            StudentSubjectEnrollment.academic_scheme_id == subject.academic_scheme_id,
            StudentSubjectEnrollment.semester_id == subject.semester_id,
            StudentSubjectEnrollment.active.is_(True),
        )
    ).first()
    offering = db.get(BranchSubjectOffering, (profile.branch_id, subject.id))
    if enrollment is None or offering is None or not offering.active:
        raise HTTPException(status_code=403, detail="This content is not available for your enrollment")


def _require_published_version(db: Session, unit: Unit) -> None:
    if not unit.active or unit.verification_status != VerificationStatus.VERIFIED:
        raise HTTPException(status_code=404, detail="Unit not found")
    version_id = db.scalars(
        select(SyllabusVersion.id).where(
            SyllabusVersion.id == unit.syllabus_version_id,
            SyllabusVersion.subject_id == unit.subject_id,
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusVersion.source_verification_status == "VERIFIED",
        )
    ).first()
    if version_id is None or unit.source_verification_status != "VERIFIED":
        raise HTTPException(status_code=404, detail="Unit not found")
