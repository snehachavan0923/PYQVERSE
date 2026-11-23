import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import (
    bearer_token,
    create_supabase_anon_client,
    normalize_admin_email,
    rate_limit,
    registration_error_response,
    validate_student_email,
    verify_bootstrap_token,
    password_login_error_response,
    create_supabase_service_client,
)
from app.database.connection import get_db
from app.models.academic import (
    AcademicScheme,
    Branch,
    ElectiveOption,
    Semester,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.user import AccountStatus, User, UserRole
from app.models.bootstrap import AdministratorBootstrapRecord
from app.models.document import LearningResource, QuestionPaper, UploadedDocument, ExamType
from app.models.syllabus import VerificationStatus
from app.models.question import ContentReview
from app.services.storage import create_signed_download, upload_private_object
from app.schemas.auth import (
    BootstrapAdminRequest,
    LoginRequest,
    OnboardingRequest,
    RefreshRequest,
    RegisterRequest,
    SendOtpRequest,
    VerifyOtpRequest,
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
            "options": {"data": {"full_name": payload.full_name}},
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
        full_name=payload.full_name,
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


@router.post("/send-otp")
def send_otp(payload: SendOtpRequest, request: Request):
    rate_limit(f"otp:{payload.email}:{request.client.host if request.client else 'unknown'}")
    email = validate_student_email(str(payload.email)) if payload.purpose == "signup" else str(payload.email).lower()
    client = create_supabase_anon_client()
    try:
        if payload.purpose == "signup":
            client.auth.sign_up({
                "email": email,
                "password": secrets.token_urlsafe(32),
            })
        else:
            client.auth.sign_in_with_otp({"email": email})
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to send verification OTP") from exc
    return {"message": "If the email is permitted, a verification OTP will be sent"}


@router.post("/verify-otp")
def verify_otp(payload: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"verify:{payload.email}:{request.client.host if request.client else 'unknown'}")
    email = str(payload.email).lower()
    client = create_supabase_anon_client()
    otp_type = "signup" if payload.purpose == "signup" else "email"
    try:
        response = client.auth.verify_otp({"email": email, "token": payload.token, "type": otp_type})
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP") from exc

    session = session_payload(response)
    access_token = session["access_token"]
    if not access_token:
        raise HTTPException(status_code=401, detail="OTP verification did not create a session")
    user, _ = synchronized_user(db, access_token)
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    return {
        **session,
        "profile": {
            "id": str(user.id),
            "role": user.role.value,
            "onboarding_completed": bool(profile and profile.profile_completed),
        },
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"login:{payload.email}:{request.client.host if request.client else 'unknown'}")
    email = str(payload.email).lower()
    client = create_supabase_anon_client()
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": payload.password})
    except Exception as exc:
        raise password_login_error_response(exc) from exc

    session = session_payload(response)
    if not session["access_token"]:
        raise HTTPException(status_code=401, detail="Login did not create a session")
    user, _ = synchronized_user(db, session["access_token"])
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    return {
        **session,
        "profile": {
            "id": str(user.id),
            "role": user.role.value,
            "onboarding_completed": bool(profile and profile.profile_completed),
        },
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
        client.auth.sign_out(access_token)
    except Exception:
        pass
    return {"message": "Logged out"}


@router.post("/bootstrap-admin")
def bootstrap_admin(payload: BootstrapAdminRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"bootstrap:{request.client.host if request.client else 'unknown'}", limit=3)
    verify_bootstrap_token(payload.bootstrap_token)
    if db.scalars(select(User).where(User.role == UserRole.ADMIN_FACULTY)).first():
        raise HTTPException(status_code=409, detail="Administrator is already configured")

    email = normalize_admin_email(str(payload.email))
    client = create_supabase_anon_client()
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": secrets.token_urlsafe(32),
            "options": {"data": {"requested_role": "ADMIN_FACULTY"}},
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Administrator verification could not be started") from exc

    auth_user = getattr(response, "user", None)
    if auth_user is None:
        raise HTTPException(status_code=400, detail="Supabase did not create an identity")
    user = User(
        supabase_auth_id=uuid.UUID(str(auth_user.id)),
        full_name=email,
        email=email,
        email_verified=False,
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    db.add(AdministratorBootstrapRecord(
        email=email,
        supabase_auth_id=user.supabase_auth_id,
    ))
    db.commit()
    db.refresh(user)
    return {
        "message": "Administrator verification started",
        "email": email,
        "email_verification_pending": True,
    }


@router.get("/me")
def me(access_token: str = Depends(bearer_token), db: Session = Depends(get_db)):
    user, auth_user = synchronized_user(db, access_token)
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
        elective_option = db.scalars(
            select(ElectiveOption).where(
                ElectiveOption.subject_id == elective.id,
            )
        ).first()
        if not elective_option:
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

    for subject in db.scalars(
        select(Subject).where(
            Subject.academic_scheme_id == scheme.id,
            Subject.semester_id == semester.id,
            Subject.subject_type == "CORE",
            Subject.active.is_(True),
        )
    ).all():
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
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=409, detail="Student onboarding is required")

    branch = db.get(Branch, profile.branch_id) if profile.branch_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    elective = db.get(Subject, profile.selected_elective_id) if profile.selected_elective_id else None
    enrollments = db.scalars(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.active.is_(True),
        )
    ).all()
    subjects = [db.get(Subject, enrollment.subject_id) for enrollment in enrollments]
    return {
        "welcome_name": profile.student_name,
        "profile": {
            "usn": profile.usn,
            "department": branch.name if branch else None,
            "semester": semester.name if semester else None,
            "selected_elective": elective.name if elective else None,
            "onboarding_completed": profile.profile_completed,
        },
        "enrolled_subjects": [
            {"id": str(subject.id), "code": subject.code, "name": subject.name}
            for subject in subjects
            if subject
        ],
        "academic_preparation": {"status": "Ready", "progress_available": False},
        "progress": {"started_topics": 0, "completed_topics": 0, "bookmarked_topics": 0},
        "recent_activity": [],
    }


@router.get("/student/profile")
def student_profile(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return {
        "id": str(profile.id),
        "student_name": profile.student_name,
        "usn": profile.usn,
        "branch_id": str(profile.branch_id) if profile.branch_id else None,
        "academic_scheme_id": str(profile.academic_scheme_id) if profile.academic_scheme_id else None,
        "current_semester_id": str(profile.current_semester_id) if profile.current_semester_id else None,
        "selected_elective_id": str(profile.selected_elective_id) if profile.selected_elective_id else None,
        "enrollment_year": profile.enrollment_year,
        "profile_completed": profile.profile_completed,
    }


@router.get("/admin/dashboard")
def admin_dashboard(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    subject_count = db.scalar(select(func.count()).select_from(Subject).where(Subject.active.is_(True))) or 0
    student_count = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.STUDENT)) or 0
    admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN_FACULTY)) or 0
    branch_count = db.scalar(select(func.count()).select_from(Branch).where(Branch.active.is_(True))) or 0
    scheme_count = db.scalar(select(func.count()).select_from(AcademicScheme).where(AcademicScheme.active.is_(True))) or 0
    semester_count = db.scalar(select(func.count()).select_from(Semester).where(Semester.active.is_(True))) or 0
    uploaded_count = db.scalar(select(func.count()).select_from(UploadedDocument)) or 0
    pyq_count = db.scalar(select(func.count()).select_from(QuestionPaper)) or 0
    pending_review_count = db.scalar(select(func.count()).select_from(ContentReview).where(ContentReview.status == VerificationStatus.PENDING)) or 0
    return {
        "welcome_name": user.full_name,
        "profile": {"email": user.email, "role": user.role.value},
        "catalog_overview": {"subjects": subject_count, "semesters": semester_count, "branches": branch_count, "schemes": scheme_count},
        "user_overview": {"students": student_count, "administrators": admin_count},
        "student_overview": {"students": student_count},
        "content_overview": {"uploaded_documents": uploaded_count, "pyq_papers": pyq_count, "learning_resources": 0, "pending_reviews": pending_review_count},
        "document_management_available": False,
    }


@router.get("/admin/academic/subjects")
def admin_subjects(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    statement = select(Subject)
    if search:
        pattern = f"%{search.lower()}%"
        statement = statement.where(
            Subject.code.ilike(pattern) | Subject.name.ilike(pattern)
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.order_by(Subject.code).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "code": item.code,
                "name": item.name,
                "subject_type": item.subject_type,
                "active": item.active,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/admin/users")
def admin_users(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    statement = select(User)
    if search:
        pattern = f"%{search.lower()}%"
        statement = statement.where(
            User.full_name.ilike(pattern) | User.email.ilike(pattern)
        )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "full_name": item.full_name,
                "email": item.email,
                "role": item.role.value,
                "account_status": item.account_status.value,
                "email_verified": item.email_verified,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/auth/student/subjects")
def student_subjects(
    search: str = "",
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=409, detail="Student onboarding is required")
    statement = (
        select(Subject)
        .join(StudentSubjectEnrollment, StudentSubjectEnrollment.subject_id == Subject.id)
        .where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.active.is_(True),
            Subject.active.is_(True),
        )
    )
    if search:
        pattern = f"%{search.lower()}%"
        statement = statement.where(Subject.code.ilike(pattern) | Subject.name.ilike(pattern))
    items = db.scalars(statement.order_by(Subject.code)).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "code": item.code,
                "name": item.name,
                "subject_type": item.subject_type,
                "semester_id": str(item.semester_id),
            }
            for item in items
        ],
        "total": len(items),
    }


@router.get("/auth/student/profile")
def current_student_profile(
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Student profile not found")
    branch = db.get(Branch, profile.branch_id) if profile.branch_id else None
    scheme = db.get(AcademicScheme, profile.academic_scheme_id) if profile.academic_scheme_id else None
    semester = db.get(Semester, profile.current_semester_id) if profile.current_semester_id else None
    elective = db.get(Subject, profile.selected_elective_id) if profile.selected_elective_id else None
    return {
        "email": user.email,
        "full_name": profile.student_name,
        "usn": profile.usn,
        "branch": branch.name if branch else None,
        "academic_scheme": scheme.name if scheme else None,
        "semester": semester.name if semester else None,
        "selected_elective": elective.name if elective else None,
        "profile_completed": profile.profile_completed,
    }


@router.post("/admin/resources")
def upload_learning_resource(
    title: str,
    subject_id: uuid.UUID,
    semester_id: uuid.UUID,
    resource_type: str,
    description: str = "",
    published: bool = False,
    file: UploadFile = File(...),
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.ADMIN_FACULTY)
    subject = db.get(Subject, subject_id)
    semester = db.get(Semester, semester_id)
    if not subject or not semester:
        raise HTTPException(status_code=400, detail="Invalid subject or semester")
    if resource_type not in {"NOTES", "STUDY_MATERIAL", "REFERENCE", "IMPORTANT_QUESTIONS"}:
        raise HTTPException(status_code=422, detail="Invalid resource type")

    storage_path, content, file_type = upload_private_object("learning-resources", file)
    try:
        resource = LearningResource(
            title=title,
            description=description or None,
            subject_id=subject_id,
            semester_id=semester_id,
            resource_type=resource_type,
            storage_path=storage_path,
            original_filename=file.filename or "document",
            file_type=file_type,
            file_size=len(content),
            published=published,
            uploaded_by=user.id,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
    except Exception as exc:
        db.rollback()
        try:
            create_supabase_service_client().storage.from_("pyqverse-private").remove([storage_path])
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Unable to save resource metadata") from exc
    return {"id": str(resource.id), "title": resource.title, "published": resource.published}


@router.get("/auth/student/resources")
def student_resources(
    search: str = "",
    subject_id: uuid.UUID | None = None,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    statement = select(LearningResource).where(LearningResource.published.is_(True))
    if subject_id:
        statement = statement.where(LearningResource.subject_id == subject_id)
    if search:
        pattern = f"%{search.lower()}%"
        statement = statement.where(
            LearningResource.title.ilike(pattern) | LearningResource.description.ilike(pattern)
        )
    items = db.scalars(statement.order_by(LearningResource.uploaded_at.desc())).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "description": item.description,
                "resource_type": item.resource_type,
                "subject_id": str(item.subject_id),
                "semester_id": str(item.semester_id),
            }
            for item in items
        ],
        "total": len(items),
    }


@router.get("/auth/student/resources/{resource_id}/download")
def download_student_resource(
    resource_id: uuid.UUID,
    access_token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
):
    user, _ = synchronized_user(db, access_token)
    require_role(user, UserRole.STUDENT)
    resource = db.get(LearningResource, resource_id)
    if not resource or not resource.published:
        raise HTTPException(status_code=404, detail="Resource not found")
    profile = db.scalars(select(StudentProfile).where(StudentProfile.user_id == user.id)).first()
    if not profile:
        raise HTTPException(status_code=403, detail="Student profile is required")
    if profile.current_semester_id and resource.semester_id != profile.current_semester_id:
        raise HTTPException(status_code=403, detail="Resource is outside your academic configuration")
    return {"download_url": create_signed_download(resource.storage_path)}
