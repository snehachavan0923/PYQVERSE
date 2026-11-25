import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    bearer_token,
    create_supabase_anon_client,
    create_supabase_service_client,
    log_supabase_auth_error,
    rate_limit,
    registration_error_response,
    validate_student_email,
)
from app.database.connection import get_db
from app.models.academic import (
    AcademicScheme,
    Branch,
    BranchSubjectOffering,
    ElectiveBasket,
    ElectiveOption,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.document import PermissionStatus, QuestionPaper, UploadedDocument
from app.models.question import ContentReview
from app.models.resource import LearningResource
from app.models.syllabus import SyllabusDocument, SyllabusVersion, VerificationStatus
from app.models.user import AccountStatus, User, UserRole
from app.schemas.admin import (
    AdminProfileUpdateRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
)
from app.schemas.auth import (
    LoginRequest,
    OnboardingRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.services.auth import require_role, synchronized_user


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def session_payload(response):
    session = getattr(response, "session", None)
    user = getattr(response, "user", None)
    if isinstance(session, dict):
        access_token = session.get("access_token")
        refresh_token = session.get("refresh_token")
    else:
        access_token = getattr(session, "access_token", None)
        refresh_token = getattr(session, "refresh_token", None)
    if isinstance(user, dict):
        user_id = user.get("id")
        email = user.get("email")
        confirmed = user.get("email_confirmed_at") or user.get("confirmed_at")
    else:
        user_id = getattr(user, "id", None)
        email = getattr(user, "email", None)
        confirmed = getattr(user, "email_confirmed_at", None) or getattr(user, "confirmed_at", None)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": str(user_id) if user_id else None,
            "email": email,
            "email_verified": bool(confirmed),
        },
    }


def _profile_payload(db: Session, user: User) -> dict:
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    return {
        "id": str(user.id),
        "role": user.role.value,
        "onboarding_completed": bool(profile and profile.profile_completed),
    }


def _student_profile(db: Session, user: User) -> StudentProfile:
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=409, detail="Student onboarding is required")
    return profile


def _enrolled_subjects(db: Session, profile: StudentProfile) -> list[Subject]:
    enrollments = db.scalars(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.active.is_(True),
        )
    ).all()
    subject_ids = [enrollment.subject_id for enrollment in enrollments]
    if not subject_ids:
        return []
    subjects = db.scalars(
        select(Subject).where(Subject.id.in_(subject_ids), Subject.active.is_(True))
    ).all()
    order = {subject_id: index for index, subject_id in enumerate(subject_ids)}
    return sorted(subjects, key=lambda subject: order.get(subject.id, len(order)))


def _core_subjects_for_branch(
    db: Session,
    branch: Branch | None,
    scheme: AcademicScheme,
    semester: Semester,
) -> list[Subject]:
    statement = select(Subject).where(
        Subject.academic_scheme_id == scheme.id,
        Subject.semester_id == semester.id,
        Subject.subject_type == "CORE",
        Subject.active.is_(True),
        or_(
            Subject.source_verification_status.is_(None),
            Subject.source_verification_status == "VERIFIED",
        ),
    )
    if branch:
        offered_ids = db.scalars(
            select(BranchSubjectOffering.subject_id)
            .join(Subject, Subject.id == BranchSubjectOffering.subject_id)
            .where(
                BranchSubjectOffering.branch_id == branch.id,
                BranchSubjectOffering.active.is_(True),
                Subject.academic_scheme_id == scheme.id,
                Subject.semester_id == semester.id,
                Subject.active.is_(True),
            )
        ).all()
        if offered_ids:
            statement = statement.where(Subject.id.in_(offered_ids))
    return db.scalars(statement).all()


def _has_elective_option_for_branch(
    db: Session,
    subject: Subject,
    scheme: AcademicScheme,
    semester: Semester,
    branch: Branch | None,
) -> bool:
    branch_scope = (
        or_(ElectiveBasket.branch_id == branch.id, ElectiveBasket.branch_id.is_(None))
        if branch
        else ElectiveBasket.branch_id.is_(None)
    )
    return (
        db.scalars(
            select(ElectiveOption)
            .join(ElectiveBasket, ElectiveBasket.id == ElectiveOption.basket_id)
            .join(Subject, Subject.id == ElectiveOption.subject_id)
            .where(
                ElectiveOption.subject_id == subject.id,
                ElectiveBasket.academic_scheme_id == scheme.id,
                ElectiveBasket.semester_id == semester.id,
                ElectiveBasket.active.is_(True),
                or_(
                    Subject.source_verification_status.is_(None),
                    Subject.source_verification_status == "VERIFIED",
                ),
                branch_scope,
            )
        ).first()
        is not None
    )


def _subject_summaries(db: Session, profile: StudentProfile) -> list[dict]:
    subjects = _enrolled_subjects(db, profile)
    if not subjects:
        return []
    subject_ids = [subject.id for subject in subjects]

    syllabus_rows = db.scalars(
        select(SyllabusVersion.subject_id)
        .join(SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id)
        .where(
            SyllabusVersion.subject_id.in_(subject_ids),
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusDocument.active.is_(True),
            SyllabusDocument.verification_status == VerificationStatus.VERIFIED,
        )
    ).all()
    subjects_with_syllabus = set(syllabus_rows)

    pyq_rows = db.execute(
        select(QuestionPaper.subject_id, func.count(QuestionPaper.id))
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            QuestionPaper.subject_id.in_(subject_ids),
            UploadedDocument.active.is_(True),
            UploadedDocument.verification_status == VerificationStatus.VERIFIED,
            UploadedDocument.permission_status == PermissionStatus.APPROVED,
        )
        .group_by(QuestionPaper.subject_id)
    ).all()
    pyq_counts = {row[0]: row[1] for row in pyq_rows}

    resource_rows = db.execute(
        select(LearningResource.subject_id, func.count(LearningResource.id))
        .where(
            LearningResource.subject_id.in_(subject_ids),
            LearningResource.active.is_(True),
            LearningResource.verification_status == VerificationStatus.VERIFIED,
        )
        .group_by(LearningResource.subject_id)
    ).all()
    resource_counts = {row[0]: int(row[1]) for row in resource_rows}

    semester_ids = {subject.semester_id for subject in subjects}
    semesters = {
        semester.id: semester
        for semester in db.scalars(select(Semester).where(Semester.id.in_(semester_ids))).all()
    }

    summaries = []
    for subject in subjects:
        semester = semesters.get(subject.semester_id)
        pyq_count = int(pyq_counts.get(subject.id, 0))
        resource_count = int(resource_counts.get(subject.id, 0))
        summaries.append({
            "id": str(subject.id),
            "code": subject.code,
            "name": subject.name,
            "subject_type": subject.subject_type,
            "credits": subject.credits,
            "semester": semester.name if semester else None,
            "semester_number": semester.number if semester else None,
            "syllabus_available": subject.id in subjects_with_syllabus,
            "pyq_count": pyq_count,
            "pyq_available": pyq_count > 0,
            "learning_resources_available": resource_count > 0,
            "learning_resource_count": resource_count,
        })
    return summaries


def _count(db: Session, model, *criteria) -> int:
    statement = select(func.count()).select_from(model)
    if criteria:
        statement = statement.where(*criteria)
    return int(db.scalar(statement) or 0)


@router.post("/register")
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"register:{request.client.host if request.client else 'unknown'}")
    email = validate_student_email(str(payload.email))
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    client = create_supabase_anon_client()
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": payload.password,
            "options": {"data": {"full_name": payload.full_name.strip()}},
        })
    except Exception as exc:
        raise registration_error_response(exc) from exc

    auth_user = getattr(response, "user", None)
    if auth_user is None:
        raise HTTPException(status_code=400, detail="Supabase did not create a user")
    auth_id = getattr(auth_user, "id", None)
    if not auth_id:
        raise HTTPException(status_code=400, detail="Supabase identity is missing")

    confirmed = getattr(auth_user, "email_confirmed_at", None) or getattr(auth_user, "confirmed_at", None)
    user = User(
        supabase_auth_id=uuid.UUID(str(auth_id)),
        full_name=payload.full_name.strip(),
        email=email,
        email_verified=bool(confirmed),
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        **session_payload(response),
        "profile": {"id": str(user.id), "role": "STUDENT", "onboarding_completed": False},
        "email_verification_pending": not bool(confirmed),
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"login:{payload.email}:{request.client.host if request.client else 'unknown'}")
    email = str(payload.email).lower()
    client = create_supabase_anon_client()
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": payload.password})
    except Exception as exc:
        _, error_code = log_supabase_auth_error("login", exc)
        if (error_code or "").lower() in {"email_not_confirmed", "email_not_verified"}:
            raise HTTPException(
                status_code=403,
                detail="Please confirm your email before signing in.",
            ) from exc
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    session = session_payload(response)
    if not session["access_token"]:
        raise HTTPException(status_code=401, detail="Login did not create a session")
    user, _ = synchronized_user(db, session["access_token"])
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {
        **session,
        "profile": _profile_payload(db, user),
    }


@router.post("/refresh")
def refresh(payload: RefreshRequest):
    client = create_supabase_anon_client()
    try:
        response = client.auth.refresh_session(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session") from exc
    return session_payload(response)


@router.post("/logout")
def logout(access_token: str = Depends(bearer_token)):
    client = create_supabase_anon_client()
    try:
        client.auth.admin.sign_out(access_token)
    except Exception:
        # Local session cleanup still proceeds on the client.
        pass
    return {"message": "Logged out"}


@router.post("/password-reset/request")
def request_password_reset(payload: PasswordResetRequest, request: Request):
    rate_limit(f"password-reset:{payload.email}:{request.client.host if request.client else 'unknown'}")
    email = str(payload.email).lower()
    client = create_supabase_anon_client()
    try:
        client.auth.reset_password_for_email(
            email,
            {"redirect_to": f"{settings.FRONTEND_URL.rstrip('/')}/reset-password"},
        )
    except Exception as exc:
        # Always return the same message so account existence is not disclosed.
        log_supabase_auth_error("password-reset", exc)
    return {
        "message": "If an account exists for this email, a password reset link has been sent.",
    }


@router.get("/me")
def me(access_token: str = Depends(bearer_token), db: Session = Depends(get_db)):
    user, _ = synchronized_user(db, access_token)
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "email_verified": user.email_verified,
        "account_status": user.account_status.value,
        "onboarding_completed": bool(profile and profile.profile_completed),
    }


@router.post("/student/onboarding")
def student_onboarding(
    payload: OnboardingRequest,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)

    branch = db.get(Branch, payload.branch_id)
    scheme = db.get(AcademicScheme, payload.academic_scheme_id)
    semester = db.get(Semester, payload.semester_id)
    if not branch or not branch.active:
        raise HTTPException(status_code=400, detail="Invalid department")
    if not scheme or not scheme.active:
        raise HTTPException(status_code=400, detail="Invalid academic scheme")
    if branch.college_id != scheme.college_id:
        raise HTTPException(status_code=400, detail="Branch and academic scheme belong to different colleges")
    if not semester or not semester.active or semester.academic_scheme_id != scheme.id:
        raise HTTPException(status_code=400, detail="Invalid semester")

    if payload.usn:
        existing = db.scalars(select(StudentProfile).where(StudentProfile.usn == payload.usn)).first()
        if existing and existing.user_id != user.id:
            raise HTTPException(status_code=409, detail="USN is already in use")

    elective = None
    if payload.selected_elective_id:
        elective = db.get(Subject, payload.selected_elective_id)
        if (
            not elective
            or not elective.active
            or elective.subject_type != "ELECTIVE"
            or elective.academic_scheme_id != scheme.id
            or elective.semester_id != semester.id
        ):
            raise HTTPException(status_code=400, detail="Invalid elective for this academic configuration")
        if not _has_elective_option_for_branch(db, elective, scheme, semester, branch):
            raise HTTPException(status_code=400, detail="Selected subject is not an elective option")

    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if profile is None:
        profile = StudentProfile(
            user_id=user.id,
            student_name=payload.full_name,
        )
        db.add(profile)

    profile.student_name = payload.full_name
    profile.usn = payload.usn
    profile.branch_id = branch.id
    profile.academic_scheme_id = scheme.id
    profile.current_semester_id = semester.id
    profile.selected_elective_id = elective.id if elective else None
    profile.enrollment_year = payload.enrollment_year
    profile.profile_completed = True
    user.full_name = payload.full_name
    db.flush()

    for subject in _core_subjects_for_branch(db, branch, scheme, semester):
        enrollment = db.scalars(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_profile_id == profile.id,
                StudentSubjectEnrollment.subject_id == subject.id,
            )
        ).first()
        if enrollment is None:
            db.add(StudentSubjectEnrollment(
                student_profile_id=profile.id,
                subject_id=subject.id,
                semester_id=semester.id,
                academic_scheme_id=scheme.id,
                is_elective=False,
            ))

    if elective:
        enrollment = db.scalars(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_profile_id == profile.id,
                StudentSubjectEnrollment.subject_id == elective.id,
            )
        ).first()
        if enrollment is None:
            db.add(StudentSubjectEnrollment(
                student_profile_id=profile.id,
                subject_id=elective.id,
                semester_id=semester.id,
                academic_scheme_id=scheme.id,
                is_elective=True,
            ))

    db.commit()
    db.refresh(profile)
    return {"message": "Student onboarding completed", "profile_id": str(profile.id)}


@router.get("/student/dashboard")
def student_dashboard(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)

    branch = db.get(Branch, profile.branch_id) if profile.branch_id else None
    scheme = db.get(AcademicScheme, profile.academic_scheme_id) if profile.academic_scheme_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    elective = db.get(Subject, profile.selected_elective_id) if profile.selected_elective_id else None
    subjects = _subject_summaries(db, profile)

    return {
        "welcome_name": profile.student_name,
        "profile": {
            "usn": profile.usn,
            "department": branch.name if branch else None,
            "branch": branch.name if branch else None,
            "academic_scheme": scheme.name if scheme else None,
            "semester": semester.name if semester else None,
            "semester_number": semester.number if semester else None,
            "selected_elective": elective.name if elective else None,
            "enrollment_year": profile.enrollment_year,
            "onboarding_completed": profile.profile_completed,
        },
        "academic_overview": {
            "current_semester": semester.name if semester else None,
            "enrolled_subjects": len(subjects),
            "subjects_with_syllabus": sum(1 for item in subjects if item["syllabus_available"]),
            "subjects_with_pyqs": sum(1 for item in subjects if item["pyq_available"]),
            "subjects_with_resources": sum(1 for item in subjects if item["learning_resources_available"]),
            "learning_resources_available": any(item["learning_resources_available"] for item in subjects),
            "learning_resource_count": sum(item["learning_resource_count"] for item in subjects),
            "pyq_count": sum(item["pyq_count"] for item in subjects),
        },
        "subjects": subjects,
        "enrolled_subjects": [
            {"id": item["id"], "code": item["code"], "name": item["name"]}
            for item in subjects
        ],
        "academic_preparation": {
            "status": "Ready" if subjects else "Pending",
            "progress_available": False,
        },
        "progress": {"started_topics": 0, "completed_topics": 0, "bookmarked_topics": 0},
        "recent_activity": [],
    }


@router.get("/student/subjects")
def student_subjects(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)
    subjects = _subject_summaries(db, profile)
    return {"subjects": subjects, "count": len(subjects)}


@router.get("/student/syllabus")
def student_syllabus(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)
    subjects = _enrolled_subjects(db, profile)
    if not subjects:
        return {"documents": [], "count": 0}

    subject_ids = [subject.id for subject in subjects]
    subject_map = {subject.id: subject for subject in subjects}
    rows = db.execute(
        select(SyllabusVersion, SyllabusDocument)
        .join(SyllabusDocument, SyllabusDocument.syllabus_version_id == SyllabusVersion.id)
        .where(
            SyllabusVersion.subject_id.in_(subject_ids),
            SyllabusVersion.active.is_(True),
            SyllabusVersion.verification_status == VerificationStatus.VERIFIED,
            SyllabusDocument.active.is_(True),
            SyllabusDocument.verification_status == VerificationStatus.VERIFIED,
        )
        .order_by(SyllabusVersion.subject_id, SyllabusVersion.version)
    ).all()
    documents = []
    for version, document in rows:
        subject = subject_map.get(version.subject_id)
        documents.append({
            "id": str(document.id),
            "subject_id": str(version.subject_id),
            "subject_code": subject.code if subject else None,
            "subject_name": subject.name if subject else None,
            "version": version.version,
            "original_filename": document.original_filename,
            "file_type": document.file_type,
            "verification_status": version.verification_status.value,
        })
    return {"documents": documents, "count": len(documents)}


@router.get("/student/pyqs")
def student_pyqs(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)
    subjects = _enrolled_subjects(db, profile)
    if not subjects:
        return {"question_papers": [], "count": 0}

    subject_ids = [subject.id for subject in subjects]
    subject_map = {subject.id: subject for subject in subjects}
    papers = db.scalars(
        select(QuestionPaper)
        .join(UploadedDocument, UploadedDocument.id == QuestionPaper.uploaded_document_id)
        .where(
            QuestionPaper.subject_id.in_(subject_ids),
            UploadedDocument.active.is_(True),
            UploadedDocument.verification_status == VerificationStatus.VERIFIED,
            UploadedDocument.permission_status == PermissionStatus.APPROVED,
        )
        .order_by(QuestionPaper.examination_year.desc(), QuestionPaper.exam_type)
    ).all()
    return {
        "question_papers": [
            {
                "id": str(paper.id),
                "subject_id": str(paper.subject_id),
                "subject_code": subject_map[paper.subject_id].code if paper.subject_id in subject_map else None,
                "subject_name": subject_map[paper.subject_id].name if paper.subject_id in subject_map else None,
                "exam_type": paper.exam_type.value,
                "cie_number": paper.cie_number,
                "examination_year": paper.examination_year,
            }
            for paper in papers
        ],
        "count": len(papers),
    }


@router.get("/student/resources")
def student_resources(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)
    subjects = _enrolled_subjects(db, profile)
    if not subjects:
        return {"available": False, "resources": [], "count": 0, "message": "No subjects enrolled yet."}
    subject_ids = [subject.id for subject in subjects]
    subject_map = {subject.id: subject for subject in subjects}
    rows = db.scalars(
        select(LearningResource)
        .where(
            LearningResource.subject_id.in_(subject_ids),
            LearningResource.active.is_(True),
            LearningResource.verification_status == VerificationStatus.VERIFIED,
        )
        .order_by(LearningResource.uploaded_at.desc())
    ).all()
    return {
        "available": bool(rows),
        "resources": [
            {
                "id": str(item.id),
                "subject_id": str(item.subject_id),
                "subject_code": subject_map[item.subject_id].code if item.subject_id in subject_map else None,
                "subject_name": subject_map[item.subject_id].name if item.subject_id in subject_map else None,
                "title": item.title,
                "description": item.description,
                "resource_type": item.resource_type,
                "original_filename": item.original_filename,
                "uploaded_at": item.uploaded_at.isoformat() if item.uploaded_at else None,
            }
            for item in rows
        ],
        "count": len(rows),
        "message": "No learning resources uploaded yet." if not rows else None,
    }


@router.get("/student/profile")
def student_profile(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)
    branch = db.get(Branch, profile.branch_id) if profile.branch_id else None
    scheme = db.get(AcademicScheme, profile.academic_scheme_id) if profile.academic_scheme_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    elective = db.get(Subject, profile.selected_elective_id) if profile.selected_elective_id else None
    return {
        "id": str(profile.id),
        "student_name": profile.student_name,
        "email": user.email,
        "usn": profile.usn,
        "branch_id": str(profile.branch_id) if profile.branch_id else None,
        "branch": branch.name if branch else None,
        "academic_scheme_id": str(profile.academic_scheme_id) if profile.academic_scheme_id else None,
        "academic_scheme": scheme.name if scheme else None,
        "current_semester_id": str(profile.current_semester_id) if profile.current_semester_id else None,
        "semester": semester.name if semester else None,
        "selected_elective_id": str(profile.selected_elective_id) if profile.selected_elective_id else None,
        "selected_elective": elective.name if elective else None,
        "enrollment_year": profile.enrollment_year,
        "profile_completed": profile.profile_completed,
    }


def _recent_activity(db: Session, limit: int = 6) -> list[dict]:
    """Derive recent activity from real timestamps; no synthetic records."""
    activity: list[dict] = []
    for item in db.scalars(select(User).order_by(User.created_at.desc()).limit(limit)).all():
        activity.append({
            "type": "STUDENT_REGISTERED" if item.role == UserRole.STUDENT else "ADMIN_REGISTERED",
            "title": f"{item.full_name} registered",
            "detail": item.role.value,
            "at": item.created_at.isoformat() if item.created_at else None,
        })
    for item in db.scalars(
        select(SyllabusVersion).order_by(SyllabusVersion.created_at.desc()).limit(limit)
    ).all():
        subject = db.get(Subject, item.subject_id)
        activity.append({
            "type": "SYLLABUS_UPLOADED",
            "title": f"Syllabus {item.version} uploaded",
            "detail": f"{subject.code} · {subject.name}" if subject else None,
            "at": item.created_at.isoformat() if item.created_at else None,
        })
    for item in db.scalars(
        select(UploadedDocument).order_by(UploadedDocument.uploaded_at.desc()).limit(limit)
    ).all():
        subject = db.get(Subject, item.subject_id) if item.subject_id else None
        activity.append({
            "type": "PYQ_UPLOADED",
            "title": item.title or item.original_filename,
            "detail": f"{subject.code} · {item.exam_type.value}" if subject else item.exam_type.value,
            "at": item.uploaded_at.isoformat() if item.uploaded_at else None,
        })
    for item in db.scalars(
        select(LearningResource).order_by(LearningResource.uploaded_at.desc()).limit(limit)
    ).all():
        subject = db.get(Subject, item.subject_id)
        activity.append({
            "type": "RESOURCE_UPLOADED",
            "title": item.title,
            "detail": f"{subject.code} · {item.resource_type}" if subject else item.resource_type,
            "at": item.uploaded_at.isoformat() if item.uploaded_at else None,
        })
    activity.sort(key=lambda entry: entry.get("at") or "", reverse=True)
    return activity[:limit]


@router.patch("/student/profile")
def update_student_profile(
    payload: ProfileUpdateRequest,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = _student_profile(db, user)

    if payload.full_name is not None:
        name = payload.full_name.strip()
        user.full_name = name
        profile.student_name = name
    if payload.usn is not None:
        usn = payload.usn.strip() or None
        if usn:
            existing = db.scalars(
                select(StudentProfile).where(StudentProfile.usn == usn, StudentProfile.id != profile.id)
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail="USN is already in use")
        profile.usn = usn
    if payload.enrollment_year is not None:
        profile.enrollment_year = payload.enrollment_year

    branch = db.get(Branch, payload.branch_id) if payload.branch_id else (
        db.get(Branch, profile.branch_id) if profile.branch_id else None
    )
    scheme = db.get(AcademicScheme, payload.academic_scheme_id) if payload.academic_scheme_id else (
        db.get(AcademicScheme, profile.academic_scheme_id) if profile.academic_scheme_id else None
    )
    semester = db.get(Semester, payload.current_semester_id) if payload.current_semester_id else (
        db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    )
    if payload.branch_id and (branch is None or not branch.active):
        raise HTTPException(status_code=400, detail="Invalid department")
    if payload.academic_scheme_id and (scheme is None or not scheme.active):
        raise HTTPException(status_code=400, detail="Invalid academic scheme")
    if payload.current_semester_id and (semester is None or not semester.active):
        raise HTTPException(status_code=400, detail="Invalid semester")
    if branch and scheme and branch.college_id != scheme.college_id:
        raise HTTPException(status_code=400, detail="Branch and academic scheme belong to different colleges")
    if scheme and semester and semester.academic_scheme_id != scheme.id:
        raise HTTPException(status_code=400, detail="Semester does not belong to the selected scheme")

    elective = None
    elective_id = payload.selected_elective_id if payload.selected_elective_id else profile.selected_elective_id
    if elective_id:
        elective = db.get(Subject, elective_id)
        if (
            elective is None
            or not elective.active
            or elective.subject_type != "ELECTIVE"
            or (scheme and elective.academic_scheme_id != scheme.id)
            or (semester and elective.semester_id != semester.id)
        ):
            if payload.selected_elective_id:
                raise HTTPException(status_code=400, detail="Invalid elective for this academic configuration")
            elective = None
        else:
            if not scheme or not semester or not _has_elective_option_for_branch(
                db, elective, scheme, semester, branch
            ):
                if payload.selected_elective_id:
                    raise HTTPException(status_code=400, detail="Selected subject is not an elective option")
                elective = None

    profile.branch_id = branch.id if branch else profile.branch_id
    profile.academic_scheme_id = scheme.id if scheme else profile.academic_scheme_id
    profile.current_semester_id = semester.id if semester else profile.current_semester_id
    profile.selected_elective_id = elective.id if elective else None

    if scheme and semester:
        enrolled = db.scalars(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_profile_id == profile.id
            )
        ).all()
        for row in enrolled:
            row.active = (
                row.semester_id == semester.id and row.academic_scheme_id == scheme.id
            )
        desired_subjects = _core_subjects_for_branch(db, branch, scheme, semester)
        desired = [(subject, False) for subject in desired_subjects]
        if elective:
            desired.append((elective, True))
        for subject, is_elective in desired:
            row = next((item for item in enrolled if item.subject_id == subject.id), None)
            if row is None:
                db.add(StudentSubjectEnrollment(
                    student_profile_id=profile.id,
                    subject_id=subject.id,
                    semester_id=semester.id,
                    academic_scheme_id=scheme.id,
                    is_elective=is_elective,
                    active=True,
                ))
            else:
                row.active = True
                row.is_elective = is_elective
                row.semester_id = semester.id
                row.academic_scheme_id = scheme.id

    db.commit()
    db.refresh(profile)
    branch = db.get(Branch, profile.branch_id) if profile.branch_id else None
    scheme = db.get(AcademicScheme, profile.academic_scheme_id) if profile.academic_scheme_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    elective = db.get(Subject, profile.selected_elective_id) if profile.selected_elective_id else None
    return {
        "id": str(profile.id),
        "student_name": profile.student_name,
        "email": user.email,
        "usn": profile.usn,
        "branch": branch.name if branch else None,
        "academic_scheme": scheme.name if scheme else None,
        "semester": semester.name if semester else None,
        "selected_elective": elective.name if elective else None,
        "enrollment_year": profile.enrollment_year,
        "profile_completed": profile.profile_completed,
    }


@router.post("/password/change")
def change_password(
    payload: PasswordChangeRequest,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    rate_limit(f"password-change:{user.id}", limit=5, window_seconds=600)
    if user.supabase_auth_id is None:
        raise HTTPException(status_code=409, detail="This account is not linked to an authentication identity")
    client = create_supabase_anon_client()
    try:
        client.auth.sign_in_with_password({"email": user.email, "password": payload.current_password})
    except Exception as exc:
        log_supabase_auth_error("password-change-verify", exc)
        raise HTTPException(status_code=401, detail="Current password is incorrect") from exc
    service = create_supabase_service_client()
    try:
        service.auth.admin.update_user_by_id(
            str(user.supabase_auth_id), {"password": payload.new_password}
        )
    except Exception as exc:
        log_supabase_auth_error("password-change-update", exc)
        raise HTTPException(status_code=503, detail="The password could not be updated right now") from exc
    return {"message": "Password updated successfully"}


@router.get("/admin/dashboard")
def admin_dashboard(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    return {
        "welcome_name": user.full_name,
        "profile": {"email": user.email, "role": user.role.value},
        "catalog_overview": {
            "subjects": _count(db, Subject),
            "semesters": _count(db, Semester),
            "branches": _count(db, Branch),
            "academic_schemes": _count(db, AcademicScheme),
        },
        "user_overview": {
            "students": _count(db, User, User.role == UserRole.STUDENT),
            "administrators": _count(db, User, User.role == UserRole.ADMIN_FACULTY),
        },
        "document_overview": {
            "uploaded_documents": _count(db, UploadedDocument),
            "pyqs": _count(db, QuestionPaper),
            "syllabus_documents": _count(
                db, SyllabusDocument, SyllabusDocument.active.is_(True)
            ),
            "learning_resources": _count(
                db, LearningResource, LearningResource.active.is_(True)
            ),
            "pending_reviews": _count(db, ContentReview, ContentReview.status == VerificationStatus.PENDING),
        },
        "recent_activity": _recent_activity(db),
        "document_management_available": True,
    }


@router.get("/admin/academic/branches")
def admin_branches(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    branches = db.scalars(select(Branch).order_by(Branch.code)).all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "code": item.code,
            "active": item.active,
            "college_id": str(item.college_id),
        }
        for item in branches
    ]


@router.get("/admin/academic/schemes")
def admin_schemes(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    schemes = db.scalars(select(AcademicScheme).order_by(AcademicScheme.code)).all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "code": item.code,
            "active": item.active,
            "college_id": str(item.college_id),
        }
        for item in schemes
    ]


@router.get("/admin/academic/semesters")
def admin_semesters(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    semesters = db.scalars(select(Semester).order_by(Semester.number)).all()
    return [
        {
            "id": str(item.id),
            "academic_scheme_id": str(item.academic_scheme_id),
            "number": item.number,
            "name": item.name,
            "active": item.active,
        }
        for item in semesters
    ]


@router.get("/admin/academic/subjects")
def admin_subjects(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    subjects = db.scalars(select(Subject).order_by(Subject.code)).all()
    return [
        {
            "id": str(item.id),
            "code": item.code,
            "name": item.name,
            "subject_type": item.subject_type,
            "credits": item.credits,
            "description": item.description,
            "semester_id": str(item.semester_id),
            "academic_scheme_id": str(item.academic_scheme_id),
            "active": item.active,
        }
        for item in subjects
    ]


@router.get("/admin/academic/elective-options")
def admin_elective_options(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    rows = db.execute(
        select(ElectiveBasket, ElectiveOption, Subject)
        .join(ElectiveOption, ElectiveOption.basket_id == ElectiveBasket.id)
        .join(Subject, Subject.id == ElectiveOption.subject_id)
        .order_by(ElectiveBasket.name, Subject.code)
    ).all()
    return [
        {
            "basket_id": str(basket.id),
            "basket_name": basket.name,
            "academic_scheme_id": str(basket.academic_scheme_id),
            "semester_id": str(basket.semester_id),
            "subject_id": str(subject.id),
            "subject_code": subject.code,
            "subject_name": subject.name,
            "active": basket.active and subject.active,
        }
        for basket, _option, subject in rows
    ]


@router.get("/admin/users")
def admin_users(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: str | None = Query(default=None, pattern="^(STUDENT|ADMIN_FACULTY)$"),
    status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE|SUSPENDED)$"),
    branch_id: uuid.UUID | None = Query(default=None),
    semester_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)

    base = select(User).outerjoin(StudentProfile, StudentProfile.user_id == User.id)
    filters = []
    if role:
        filters.append(User.role == UserRole(role))
    if status:
        filters.append(User.account_status == AccountStatus(status))
    if branch_id:
        filters.append(StudentProfile.branch_id == branch_id)
    if semester_id:
        filters.append(StudentProfile.current_semester_id == semester_id)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(User.email.ilike(pattern) | User.full_name.ilike(pattern))
    if filters:
        base = base.where(*filters)

    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    users = db.scalars(
        base.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    profiles = {
        profile.user_id: profile
        for profile in db.scalars(
            select(StudentProfile).where(StudentProfile.user_id.in_([item.id for item in users]))
        ).all()
    } if users else {}

    branch_ids = {profile.branch_id for profile in profiles.values() if profile.branch_id}
    semester_ids = {profile.current_semester_id for profile in profiles.values() if profile.current_semester_id}
    branches = {
        branch.id: branch
        for branch in db.scalars(select(Branch).where(Branch.id.in_(branch_ids))).all()
    } if branch_ids else {}
    semesters = {
        semester.id: semester
        for semester in db.scalars(select(Semester).where(Semester.id.in_(semester_ids))).all()
    } if semester_ids else {}

    items = []
    for item in users:
        profile = profiles.get(item.id)
        branch = branches.get(profile.branch_id) if profile and profile.branch_id else None
        semester = semesters.get(profile.current_semester_id) if profile and profile.current_semester_id else None
        items.append({
            "id": str(item.id),
            "full_name": item.full_name,
            "email": item.email,
            "role": item.role.value,
            "account_status": item.account_status.value,
            "email_verified": item.email_verified,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "last_login_at": item.last_login_at.isoformat() if item.last_login_at else None,
            "student_profile": {
                "usn": profile.usn,
                "profile_completed": profile.profile_completed,
                "branch_id": str(profile.branch_id) if profile.branch_id else None,
                "current_semester_id": str(profile.current_semester_id) if profile.current_semester_id else None,
                "branch_name": branch.name if branch else None,
                "semester_name": semester.name if semester else None,
            } if profile else None,
        })
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/admin/users/{user_id}")
def admin_user_detail(
    user_id: uuid.UUID,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    admin, _ = synchronized_user(db, access_token)
    require_role(admin, UserRole.ADMIN_FACULTY)
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="User not found")
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == item.id)).first()
    branch = db.get(Branch, profile.branch_id) if profile and profile.branch_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile and profile.current_semester_id else None
    scheme = (
        db.get(AcademicScheme, profile.academic_scheme_id)
        if profile and profile.academic_scheme_id
        else None
    )
    elective = (
        db.get(Subject, profile.selected_elective_id)
        if profile and profile.selected_elective_id
        else None
    )
    enrollments = []
    if profile is not None:
        rows = db.scalars(
            select(StudentSubjectEnrollment).where(
                StudentSubjectEnrollment.student_profile_id == profile.id,
                StudentSubjectEnrollment.active.is_(True),
            )
        ).all()
        subjects = {
            subject.id: subject
            for subject in db.scalars(
                select(Subject).where(Subject.id.in_([row.subject_id for row in rows]))
            ).all()
        } if rows else {}
        enrollments = [
            {
                "id": str(row.subject_id),
                "code": subjects[row.subject_id].code,
                "name": subjects[row.subject_id].name,
                "is_elective": row.is_elective,
            }
            for row in rows
            if row.subject_id in subjects
        ]
    return {
        "id": str(item.id),
        "full_name": item.full_name,
        "email": item.email,
        "role": item.role.value,
        "account_status": item.account_status.value,
        "email_verified": item.email_verified,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "last_login_at": item.last_login_at.isoformat() if item.last_login_at else None,
        "student_profile": {
            "usn": profile.usn,
            "profile_completed": profile.profile_completed,
            "branch": branch.name if branch else None,
            "semester": semester.name if semester else None,
            "academic_scheme": scheme.name if scheme else None,
            "selected_elective": elective.name if elective else None,
            "enrollment_year": profile.enrollment_year,
            "enrolled_subjects": enrollments,
        } if profile else None,
    }


def _admin_profile_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.value,
        "account_status": user.account_status.value,
        "email_verified": user.email_verified,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("/admin/profile")
def admin_profile(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    return _admin_profile_payload(user)


@router.patch("/admin/profile")
def update_admin_profile(
    payload: AdminProfileUpdateRequest,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    user.full_name = payload.full_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return _admin_profile_payload(user)
