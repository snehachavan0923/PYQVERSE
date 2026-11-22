from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db, test_database_connection
from app.models.academic import AcademicScheme, Branch, Semester, Subject
from app.models.syllabus import Unit, Topic
from app.schemas.academic import (
    BranchResponse,
    SemesterResponse,
    SubjectResponse,
    UnitResponse,
    TopicResponse,
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


@router.get("/api/v1/academic/schemes")
def list_schemes(db: Session = Depends(get_db)):
    return db.scalars(
        select(AcademicScheme).where(AcademicScheme.active.is_(True)).order_by(AcademicScheme.code)
    ).all()


@router.get("/api/v1/academic/semesters", response_model=list[SemesterResponse])
def list_semesters(db: Session = Depends(get_db)):
    return db.scalars(select(Semester).where(Semester.active.is_(True)).order_by(Semester.number)).all()


@router.get("/api/v1/subjects", response_model=list[SubjectResponse])
def list_subjects(db: Session = Depends(get_db)):
    return db.scalars(select(Subject).where(Subject.active.is_(True)).order_by(Subject.code)).all()


@router.get("/api/v1/subjects/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: str, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.get("/api/v1/subjects/{subject_id}/units", response_model=list[UnitResponse])
def list_units(subject_id: str, db: Session = Depends(get_db)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return db.scalars(
        select(Unit).where(Unit.subject_id == subject.id, Unit.active.is_(True)).order_by(Unit.order_index)
    ).all()


@router.get("/api/v1/units/{unit_id}/topics", response_model=list[TopicResponse])
def list_topics(unit_id: str, db: Session = Depends(get_db)):
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    return db.scalars(
        select(Topic).where(Topic.unit_id == unit.id, Topic.active.is_(True)).order_by(Topic.order_index)
    ).all()
