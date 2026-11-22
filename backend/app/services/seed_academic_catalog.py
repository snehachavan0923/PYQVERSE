from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.academic import (
    AcademicScheme,
    Branch,
    College,
    ElectiveBasket,
    ElectiveOption,
    Semester,
    Subject,
)


CORE_SUBJECTS = [
    ("MA231TC", "Linear Algebra and Probability Theory"),
    ("CS233AI", "Data Structures and Applications"),
    ("CS234AI", "Applied Digital Logic Design and Computer Organization"),
    ("CS235AT", "Operating Systems"),
    ("CS236AT", "Quantum Computing Essentials"),
]
ELECTIVES = [
    ("CV232TA", "Environment and Sustainability"),
    ("ME232TB", "Material Science for Engineers"),
    ("BT232TD", "Bioinspired Engineering"),
]


def get_or_create(db: Session, model, values: dict, *, unique_fields: tuple[str, ...]):
    filters = {field: values[field] for field in unique_fields}
    existing = db.scalars(select(model).filter_by(**filters)).first()
    if existing:
        changed = False
        for key, value in values.items():
            if getattr(existing, key) != value:
                setattr(existing, key, value)
                changed = True
        return existing, "updated" if changed else "skipped"
    record = model(**values)
    db.add(record)
    db.flush()
    return record, "inserted"


def seed() -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    with SessionLocal() as db:
        college, status = get_or_create(
            db, College, {"name": "R.V. College of Engineering", "code": "RVCE", "active": True},
            unique_fields=("code",),
        )
        counts[status] += 1

        branch, status = get_or_create(
            db, Branch,
            {"college_id": college.id, "name": "Computer Science and Engineering", "code": "CSE", "active": True},
            unique_fields=("college_id", "code"),
        )
        counts[status] += 1

        scheme, status = get_or_create(
            db, AcademicScheme,
            {"college_id": college.id, "name": "2025 Academic Scheme", "code": "2025", "active": True},
            unique_fields=("college_id", "code"),
        )
        counts[status] += 1

        semester, status = get_or_create(
            db, Semester,
            {"academic_scheme_id": scheme.id, "number": 3, "name": "Semester III", "active": True},
            unique_fields=("academic_scheme_id", "number"),
        )
        counts[status] += 1

        subject_ids = {}
        for code, name in CORE_SUBJECTS:
            subject, status = get_or_create(
                db, Subject,
                {"academic_scheme_id": scheme.id, "semester_id": semester.id, "code": code,
                 "name": name, "subject_type": "CORE", "active": True},
                unique_fields=("academic_scheme_id", "code"),
            )
            counts[status] += 1
            subject_ids[code] = subject.id

        for code, name in ELECTIVES:
            subject, status = get_or_create(
                db, Subject,
                {"academic_scheme_id": scheme.id, "semester_id": semester.id, "code": code,
                 "name": name, "subject_type": "ELECTIVE", "active": True},
                unique_fields=("academic_scheme_id", "code"),
            )
            counts[status] += 1
            subject_ids[code] = subject.id

        basket, status = get_or_create(
            db, ElectiveBasket,
            {"academic_scheme_id": scheme.id, "semester_id": semester.id,
             "name": "Semester III Elective Basket", "active": True},
            unique_fields=("academic_scheme_id", "semester_id", "name"),
        )
        counts[status] += 1

        for code, _ in ELECTIVES:
            existing = db.get(ElectiveOption, (basket.id, subject_ids[code]))
            if existing is None:
                db.add(ElectiveOption(basket_id=basket.id, subject_id=subject_ids[code]))
                counts["inserted"] += 1
            else:
                counts["skipped"] += 1

        db.commit()
    return counts


if __name__ == "__main__":
    print(seed())
