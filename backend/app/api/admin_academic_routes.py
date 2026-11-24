import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.connection import get_db
from app.models.academic import (
    AcademicScheme,
    Branch,
    College,
    ElectiveBasket,
    ElectiveOption,
    Semester,
    Subject,
)
from app.models.user import User
from app.schemas.admin import (
    BranchCreate,
    BranchUpdate,
    ElectiveBasketCreate,
    ElectiveOptionCreate,
    SchemeCreate,
    SchemeUpdate,
    SemesterCreate,
    SemesterUpdate,
    SubjectCreate,
    SubjectUpdate,
)

router = APIRouter(prefix="/api/v1/admin/academic", tags=["admin-academic"])


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def _default_college(db: Session) -> College:
    college = db.scalars(select(College).where(College.active.is_(True)).order_by(College.code)).first()
    if not college:
        raise HTTPException(status_code=409, detail="No active college is configured")
    return college


def _get_or_404(db: Session, model, record_id: uuid.UUID, label: str):
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return record


# ---------------------------------------------------------------- branches
@router.get("/branches")
def list_branches(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Branch).order_by(Branch.code)).all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "code": item.code,
            "active": item.active,
            "college_id": str(item.college_id),
        }
        for item in rows
    ]


@router.post("/branches", status_code=201)
def create_branch(
    payload: BranchCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    college = _get_or_404(db, College, payload.college_id, "College") if payload.college_id else _default_college(db)
    code = payload.code.strip().upper()
    if db.scalars(select(Branch).where(Branch.college_id == college.id, Branch.code == code)).first():
        raise HTTPException(status_code=409, detail="A branch with this code already exists")
    branch = Branch(college_id=college.id, name=payload.name.strip(), code=code, active=payload.active)
    db.add(branch)
    _commit_or_conflict(db, "A branch with this code already exists")
    db.refresh(branch)
    return {"id": str(branch.id), "name": branch.name, "code": branch.code, "active": branch.active}


@router.patch("/branches/{branch_id}")
def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    branch = _get_or_404(db, Branch, branch_id, "Branch")
    if payload.code is not None:
        code = payload.code.strip().upper()
        duplicate = db.scalars(
            select(Branch).where(
                Branch.college_id == branch.college_id, Branch.code == code, Branch.id != branch.id
            )
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A branch with this code already exists")
        branch.code = code
    if payload.name is not None:
        branch.name = payload.name.strip()
    if payload.active is not None:
        branch.active = payload.active
    _commit_or_conflict(db, "A branch with this code already exists")
    db.refresh(branch)
    return {"id": str(branch.id), "name": branch.name, "code": branch.code, "active": branch.active}


@router.delete("/branches/{branch_id}")
def deactivate_branch(
    branch_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    branch = _get_or_404(db, Branch, branch_id, "Branch")
    branch.active = False
    db.commit()
    return {"message": "Branch deactivated", "id": str(branch.id)}


# ----------------------------------------------------------------- schemes
@router.get("/schemes")
def list_schemes(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AcademicScheme).order_by(AcademicScheme.code)).all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "code": item.code,
            "active": item.active,
            "college_id": str(item.college_id),
        }
        for item in rows
    ]


@router.post("/schemes", status_code=201)
def create_scheme(
    payload: SchemeCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    college = _get_or_404(db, College, payload.college_id, "College") if payload.college_id else _default_college(db)
    code = payload.code.strip().upper()
    if db.scalars(
        select(AcademicScheme).where(AcademicScheme.college_id == college.id, AcademicScheme.code == code)
    ).first():
        raise HTTPException(status_code=409, detail="An academic scheme with this code already exists")
    scheme = AcademicScheme(college_id=college.id, name=payload.name.strip(), code=code, active=payload.active)
    db.add(scheme)
    _commit_or_conflict(db, "An academic scheme with this code already exists")
    db.refresh(scheme)
    return {"id": str(scheme.id), "name": scheme.name, "code": scheme.code, "active": scheme.active}


@router.patch("/schemes/{scheme_id}")
def update_scheme(
    scheme_id: uuid.UUID,
    payload: SchemeUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scheme = _get_or_404(db, AcademicScheme, scheme_id, "Academic scheme")
    if payload.code is not None:
        code = payload.code.strip().upper()
        duplicate = db.scalars(
            select(AcademicScheme).where(
                AcademicScheme.college_id == scheme.college_id,
                AcademicScheme.code == code,
                AcademicScheme.id != scheme.id,
            )
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="An academic scheme with this code already exists")
        scheme.code = code
    if payload.name is not None:
        scheme.name = payload.name.strip()
    if payload.active is not None:
        scheme.active = payload.active
    _commit_or_conflict(db, "An academic scheme with this code already exists")
    db.refresh(scheme)
    return {"id": str(scheme.id), "name": scheme.name, "code": scheme.code, "active": scheme.active}


@router.delete("/schemes/{scheme_id}")
def deactivate_scheme(
    scheme_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    scheme = _get_or_404(db, AcademicScheme, scheme_id, "Academic scheme")
    scheme.active = False
    db.commit()
    return {"message": "Academic scheme deactivated", "id": str(scheme.id)}


# --------------------------------------------------------------- semesters
@router.get("/semesters")
def list_semesters(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(Semester).order_by(Semester.number)).all()
    return [
        {
            "id": str(item.id),
            "number": item.number,
            "name": item.name,
            "active": item.active,
            "academic_scheme_id": str(item.academic_scheme_id),
        }
        for item in rows
    ]


@router.post("/semesters", status_code=201)
def create_semester(
    payload: SemesterCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    scheme = _get_or_404(db, AcademicScheme, payload.academic_scheme_id, "Academic scheme")
    if db.scalars(
        select(Semester).where(
            Semester.academic_scheme_id == scheme.id, Semester.number == payload.number
        )
    ).first():
        raise HTTPException(status_code=409, detail="This semester already exists for the scheme")
    semester = Semester(
        academic_scheme_id=scheme.id,
        number=payload.number,
        name=payload.name.strip(),
        active=payload.active,
    )
    db.add(semester)
    _commit_or_conflict(db, "This semester already exists for the scheme")
    db.refresh(semester)
    return {
        "id": str(semester.id),
        "number": semester.number,
        "name": semester.name,
        "active": semester.active,
    }


@router.patch("/semesters/{semester_id}")
def update_semester(
    semester_id: uuid.UUID,
    payload: SemesterUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    semester = _get_or_404(db, Semester, semester_id, "Semester")
    if payload.number is not None and payload.number != semester.number:
        duplicate = db.scalars(
            select(Semester).where(
                Semester.academic_scheme_id == semester.academic_scheme_id,
                Semester.number == payload.number,
                Semester.id != semester.id,
            )
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="This semester number is already in use")
        semester.number = payload.number
    if payload.name is not None:
        semester.name = payload.name.strip()
    if payload.active is not None:
        semester.active = payload.active
    _commit_or_conflict(db, "This semester number is already in use")
    db.refresh(semester)
    return {
        "id": str(semester.id),
        "number": semester.number,
        "name": semester.name,
        "active": semester.active,
    }


@router.delete("/semesters/{semester_id}")
def deactivate_semester(
    semester_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    semester = _get_or_404(db, Semester, semester_id, "Semester")
    semester.active = False
    db.commit()
    return {"message": "Semester deactivated", "id": str(semester.id)}


# ---------------------------------------------------------------- subjects
@router.get("/subjects")
def list_subjects(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    search: str | None = None,
    scheme_id: uuid.UUID | None = None,
    semester_id: uuid.UUID | None = None,
):
    statement = select(Subject)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(Subject.code.ilike(pattern) | Subject.name.ilike(pattern))
    if scheme_id:
        statement = statement.where(Subject.academic_scheme_id == scheme_id)
    if semester_id:
        statement = statement.where(Subject.semester_id == semester_id)
    rows = db.scalars(statement.order_by(Subject.code)).all()
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
        for item in rows
    ]


@router.post("/subjects", status_code=201)
def create_subject(
    payload: SubjectCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    scheme = _get_or_404(db, AcademicScheme, payload.academic_scheme_id, "Academic scheme")
    semester = _get_or_404(db, Semester, payload.semester_id, "Semester")
    if semester.academic_scheme_id != scheme.id:
        raise HTTPException(status_code=400, detail="Semester does not belong to the selected scheme")
    if db.scalars(
        select(Subject).where(
            Subject.academic_scheme_id == scheme.id, Subject.code == payload.code
        )
    ).first():
        raise HTTPException(status_code=409, detail="A subject with this code already exists in the scheme")
    subject = Subject(
        academic_scheme_id=scheme.id,
        semester_id=semester.id,
        code=payload.code,
        name=payload.name,
        subject_type=payload.subject_type,
        credits=payload.credits,
        description=payload.description,
        active=payload.active,
    )
    db.add(subject)
    _commit_or_conflict(db, "A subject with this code already exists in the scheme")
    db.refresh(subject)
    return {
        "id": str(subject.id),
        "code": subject.code,
        "name": subject.name,
        "subject_type": subject.subject_type,
        "semester_id": str(subject.semester_id),
        "academic_scheme_id": str(subject.academic_scheme_id),
        "active": subject.active,
    }


@router.patch("/subjects/{subject_id}")
def update_subject(
    subject_id: uuid.UUID,
    payload: SubjectUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subject = _get_or_404(db, Subject, subject_id, "Subject")
    if payload.semester_id is not None:
        semester = _get_or_404(db, Semester, payload.semester_id, "Semester")
        if semester.academic_scheme_id != subject.academic_scheme_id:
            raise HTTPException(status_code=400, detail="Semester does not belong to the subject scheme")
        subject.semester_id = semester.id
    if payload.code is not None:
        code = payload.code.strip().upper()
        duplicate = db.scalars(
            select(Subject).where(
                Subject.academic_scheme_id == subject.academic_scheme_id,
                Subject.code == code,
                Subject.id != subject.id,
            )
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A subject with this code already exists in the scheme")
        subject.code = code
    if payload.name is not None:
        subject.name = payload.name.strip()
    if payload.subject_type is not None:
        subject.subject_type = payload.subject_type
    if payload.credits is not None:
        subject.credits = payload.credits
    if payload.description is not None:
        subject.description = payload.description
    if payload.active is not None:
        subject.active = payload.active
    subject.updated_at = func.now()
    _commit_or_conflict(db, "A subject with this code already exists in the scheme")
    db.refresh(subject)
    return {
        "id": str(subject.id),
        "code": subject.code,
        "name": subject.name,
        "subject_type": subject.subject_type,
        "credits": subject.credits,
        "description": subject.description,
        "semester_id": str(subject.semester_id),
        "academic_scheme_id": str(subject.academic_scheme_id),
        "active": subject.active,
    }


@router.delete("/subjects/{subject_id}")
def deactivate_subject(
    subject_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    subject = _get_or_404(db, Subject, subject_id, "Subject")
    subject.active = False
    db.commit()
    return {"message": "Subject deactivated; historical records were preserved", "id": str(subject.id)}


# ------------------------------------------------------------- electives
@router.get("/elective-options")
def list_elective_options(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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


@router.get("/elective-baskets")
def list_elective_baskets(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ElectiveBasket).order_by(ElectiveBasket.name)).all()
    return [
        {
            "id": str(item.id),
            "name": item.name,
            "academic_scheme_id": str(item.academic_scheme_id),
            "semester_id": str(item.semester_id),
            "active": item.active,
        }
        for item in rows
    ]


@router.post("/elective-baskets", status_code=201)
def create_elective_basket(
    payload: ElectiveBasketCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scheme = _get_or_404(db, AcademicScheme, payload.academic_scheme_id, "Academic scheme")
    semester = _get_or_404(db, Semester, payload.semester_id, "Semester")
    if semester.academic_scheme_id != scheme.id:
        raise HTTPException(status_code=400, detail="Semester does not belong to the selected scheme")
    if db.scalars(
        select(ElectiveBasket).where(
            ElectiveBasket.academic_scheme_id == scheme.id,
            ElectiveBasket.semester_id == semester.id,
            ElectiveBasket.name == payload.name.strip(),
        )
    ).first():
        raise HTTPException(status_code=409, detail="This elective basket already exists")
    basket = ElectiveBasket(
        academic_scheme_id=scheme.id, semester_id=semester.id, name=payload.name.strip()
    )
    db.add(basket)
    _commit_or_conflict(db, "This elective basket already exists")
    db.refresh(basket)
    return {"id": str(basket.id), "name": basket.name, "active": basket.active}


@router.post("/elective-options", status_code=201)
def add_elective_option(
    payload: ElectiveOptionCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    basket = _get_or_404(db, ElectiveBasket, payload.basket_id, "Elective basket")
    subject = _get_or_404(db, Subject, payload.subject_id, "Subject")
    if subject.subject_type != "ELECTIVE":
        raise HTTPException(status_code=400, detail="Only ELECTIVE subjects can be basket options")
    if (
        subject.academic_scheme_id != basket.academic_scheme_id
        or subject.semester_id != basket.semester_id
    ):
        raise HTTPException(status_code=400, detail="Subject must match the basket scheme and semester")
    if db.get(ElectiveOption, (basket.id, subject.id)) is not None:
        raise HTTPException(status_code=409, detail="This elective option already exists")
    db.add(ElectiveOption(basket_id=basket.id, subject_id=subject.id))
    _commit_or_conflict(db, "This elective option already exists")
    return {
        "basket_id": str(basket.id),
        "subject_id": str(subject.id),
        "subject_code": subject.code,
        "subject_name": subject.name,
    }


@router.delete("/elective-options/{basket_id}/{subject_id}")
def remove_elective_option(
    basket_id: uuid.UUID,
    subject_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    option = db.get(ElectiveOption, (basket_id, subject_id))
    if option is None:
        raise HTTPException(status_code=404, detail="Elective option not found")
    db.delete(option)
    db.commit()
    return {"message": "Elective option removed"}
