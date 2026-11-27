"""Shared student enrollment checks for PYQ insights and learning APIs."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.academic import (
    BranchSubjectOffering,
    StudentProfile,
    StudentSubjectEnrollment,
    Subject,
)
from app.models.user import User


def get_student_profile(db: Session, user: User) -> StudentProfile:
    profile = db.scalars(
        select(StudentProfile).where(StudentProfile.user_id == user.id)
    ).first()
    if profile is None:
        raise HTTPException(status_code=409, detail="Student onboarding is required")
    return profile


def enrolled_subject_ids(db: Session, profile: StudentProfile) -> set[uuid.UUID]:
    rows = db.scalars(
        select(StudentSubjectEnrollment).where(
            StudentSubjectEnrollment.student_profile_id == profile.id,
            StudentSubjectEnrollment.active.is_(True),
        )
    ).all()
    subject_ids = {row.subject_id for row in rows}
    if profile.academic_scheme_id and profile.current_semester_id:
        core_statement = select(Subject).where(
            Subject.academic_scheme_id == profile.academic_scheme_id,
            Subject.semester_id == profile.current_semester_id,
            Subject.subject_type == "CORE",
            Subject.active.is_(True),
        )
        if profile.branch_id:
            offered_count = (
                db.scalar(
                    select(func.count(BranchSubjectOffering.subject_id)).where(
                        BranchSubjectOffering.branch_id == profile.branch_id,
                        BranchSubjectOffering.active.is_(True),
                    )
                )
                or 0
            )
            if offered_count > 0:
                core_statement = core_statement.where(
                    Subject.id.in_(
                        select(BranchSubjectOffering.subject_id).where(
                            BranchSubjectOffering.branch_id == profile.branch_id,
                            BranchSubjectOffering.active.is_(True),
                        )
                    )
                )
        for subject in db.scalars(core_statement).all():
            subject_ids.add(subject.id)
    return subject_ids


def require_subject_access(
    db: Session, user: User, subject_id: uuid.UUID
) -> tuple[StudentProfile, Subject]:
    profile = get_student_profile(db, user)
    if not profile.profile_completed:
        raise HTTPException(status_code=403, detail="Complete onboarding to access this content")
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.active:
        raise HTTPException(status_code=404, detail="Subject not found")
    if subject_id not in enrolled_subject_ids(db, profile):
        raise HTTPException(status_code=403, detail="This content is not available for your enrollment")
    return profile, subject
