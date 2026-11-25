import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.semester_iii_2025 import SEMESTER_III_SUBJECTS, SOURCE_DOCUMENT, VERSION
from app.models.academic import (
    AcademicScheme,
    Branch,
    BranchSubjectOffering,
    College,
    ElectiveBasket,
    ElectiveOption,
    Semester,
    Subject,
)
from app.models.syllabus import Subtopic, SyllabusVersion, Topic, Unit, VerificationStatus


EXPECTED_CODES = {
    "MA231TC",
    "CV232TA",
    "ME232TB",
    "BT232TD",
    "CS233AI",
    "CS234AI",
    "CS235AT",
    "CS236AT",
    "CS238DL",
    "MAT149AT",
}
ELECTIVE_OPTION_CODES = {"CV232TA", "ME232TB", "BT232TD"}
SEMESTER_III_BASKET_NAME = "Semester III shared course options"
METADATA_FIELDS = (
    "course_category",
    "course_delivery",
    "credits",
    "lecture_credits",
    "tutorial_credits",
    "practical_credits",
    "lecture_hours",
    "tutorial_hours",
    "practical_hours",
    "self_study_hours",
    "practical_component_summary",
    "source_document_reference",
    "source_page_start",
    "source_page_end",
    "source_verification_status",
    "source_notes",
)


def _stable_id(key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"pyqverse:{key}")


def validate_import_data() -> None:
    codes = {subject["code"] for subject in SEMESTER_III_SUBJECTS}
    if codes != EXPECTED_CODES:
        raise ValueError(f"Semester III code set mismatch: {sorted(codes ^ EXPECTED_CODES)}")
    if not ELECTIVE_OPTION_CODES.issubset(codes):
        raise ValueError("Elective options must reference Semester III subjects")

    for subject in SEMESTER_III_SUBJECTS:
        if subject["source_verification_status"] not in {
            "VERIFIED",
            "NEEDS_REVIEW",
            "NOT_AVAILABLE",
        }:
            raise ValueError(f"Invalid source verification status for {subject['code']}")
        if subject["source_page_start"] < 1:
            raise ValueError(f"Invalid source page for {subject['code']}")
        if subject["source_page_end"] < subject["source_page_start"]:
            raise ValueError(f"Invalid source page range for {subject['code']}")
        if subject["course_delivery"] == "THEORY_AND_PRACTICAL" and not subject["practical_hours"]:
            raise ValueError(f"{subject['code']} has no practical hours")
        for order_index, unit in enumerate(subject["units"], start=1):
            if (
                unit["hours"] < 0
                or unit["page"] < subject["source_page_start"]
                or unit["page"] > subject["source_page_end"]
            ):
                raise ValueError(f"Invalid unit metadata for {subject['code']} unit {order_index}")
            if unit.get("status", "VERIFIED") not in {
                "VERIFIED",
                "NEEDS_REVIEW",
                "NOT_AVAILABLE",
            }:
                raise ValueError(f"Invalid unit source status for {subject['code']} unit {order_index}")
            for topic in unit["topics"]:
                if topic.get("kind", "SYLLABUS") not in {"SYLLABUS", "SELF_LEARNING", "PRACTICAL"}:
                    raise ValueError(f"Invalid topic kind for {subject['code']} unit {order_index}")
                if topic.get("status", "VERIFIED") not in {
                    "VERIFIED",
                    "NEEDS_REVIEW",
                    "NOT_AVAILABLE",
                }:
                    raise ValueError(f"Invalid topic source status for {subject['code']} unit {order_index}")
                if not topic["title"].strip():
                    raise ValueError(f"Empty topic title for {subject['code']} unit {order_index}")
                topic_page = topic.get("page", unit["page"])
                if not subject["source_page_start"] <= topic_page <= subject["source_page_end"]:
                    raise ValueError(
                        f"Topic source page is outside {subject['code']}'s source range"
                    )
                for subtopic in topic.get("subtopics", ()):
                    if not subtopic["title"].strip():
                        raise ValueError(
                            f"Empty subtopic title for {subject['code']} unit {order_index}"
                        )
                    if subtopic.get("status", "VERIFIED") not in {
                        "VERIFIED",
                        "NEEDS_REVIEW",
                        "NOT_AVAILABLE",
                    }:
                        raise ValueError(
                            f"Invalid subtopic source status for {subject['code']} unit {order_index}"
                        )
                    page = subtopic.get("page", topic.get("page", unit["page"]))
                    if not subject["source_page_start"] <= page <= subject["source_page_end"]:
                        raise ValueError(
                            f"Subtopic source page is outside {subject['code']}'s source range"
                        )


def _find(db: Session, model, **filters):
    return db.scalars(select(model).filter_by(**filters)).first()


def _conflict(report: dict, key: str, detail: str) -> None:
    report["conflicts"].append({"record": key, "detail": detail})


def _record(report: dict, group: str, key: str, action: str) -> None:
    report[group][action] += 1
    report["records"].append({"record": key, "action": action})


def _ensure_identity(
    db: Session,
    model,
    *,
    filters: dict,
    values: dict,
    stable_key: str,
    report: dict,
    record_key: str,
):
    existing = _find(db, model, **filters)
    if existing is None:
        record = model(id=_stable_id(stable_key), **values)
        db.add(record)
        db.flush()
        _record(report, "catalog", record_key, "created")
        return record

    for field, expected in values.items():
        if getattr(existing, field) != expected:
            _conflict(
                report,
                record_key,
                f"Existing {field} differs; record was not changed.",
            )
            return None
    _record(report, "catalog", record_key, "unchanged")
    return existing


def _ensure_subject(db: Session, scheme: AcademicScheme, semester: Semester, data: dict, report: dict):
    key = f"subject:{scheme.code}:{data['code']}"
    metadata = {field: data.get(field) for field in METADATA_FIELDS}
    metadata["source_document_reference"] = SOURCE_DOCUMENT
    subject = _find(
        db,
        Subject,
        academic_scheme_id=scheme.id,
        code=data["code"],
    )
    expected_identity = {
        "semester_id": semester.id,
        "name": data["name"],
        "subject_type": data["subject_type"],
    }
    if subject is None:
        values = {
            "id": _stable_id(key),
            "academic_scheme_id": scheme.id,
            "semester_id": semester.id,
            "code": data["code"],
            "name": data["name"],
            "subject_type": data["subject_type"],
            "active": True,
            **metadata,
        }
        subject = Subject(**values)
        db.add(subject)
        db.flush()
        _record(report, "catalog", key, "created")
        return subject

    differences = [
        field for field, expected in expected_identity.items()
        if getattr(subject, field) != expected
    ]
    differences.extend(
        field for field in METADATA_FIELDS
        if getattr(subject, field) is not None and getattr(subject, field) != metadata[field]
    )
    if differences:
        _conflict(report, key, f"Existing values differ for: {', '.join(sorted(set(differences)))}.")
        return None

    missing = [
        field for field in METADATA_FIELDS
        if getattr(subject, field) is None and metadata[field] is not None
    ]
    for field in missing:
        setattr(subject, field, metadata[field])
    if missing:
        db.flush()
        _record(report, "catalog", key, "enriched")
    else:
        _record(report, "catalog", key, "unchanged")
    return subject


def _ensure_offering(db: Session, branch: Branch, subject: Subject, report: dict) -> bool:
    key = f"offering:{branch.code}:{subject.code}"
    existing = db.get(BranchSubjectOffering, (branch.id, subject.id))
    if existing is None:
        db.add(BranchSubjectOffering(branch_id=branch.id, subject_id=subject.id, active=True))
        db.flush()
        _record(report, "catalog", key, "created")
        return True
    if not existing.active:
        _conflict(report, key, "Existing offering is inactive; it was not reactivated.")
        return False
    _record(report, "catalog", key, "unchanged")
    return True


def _ensure_basket(db: Session, scheme: AcademicScheme, semester: Semester, branch: Branch, report: dict):
    filters = {
        "academic_scheme_id": scheme.id,
        "semester_id": semester.id,
        "branch_id": branch.id,
        "name": SEMESTER_III_BASKET_NAME,
    }
    basket = _find(db, ElectiveBasket, **filters)
    key = f"elective-basket:{scheme.code}:{semester.number}:{branch.code}"
    if basket is None:
        basket = ElectiveBasket(
            id=_stable_id(key),
            **filters,
            active=True,
        )
        db.add(basket)
        db.flush()
        _record(report, "catalog", key, "created")
    elif not basket.active:
        _conflict(report, key, "Existing basket is inactive; it was not reactivated.")
        return None
    else:
        _record(report, "catalog", key, "unchanged")
    return basket


def _ensure_syllabus_version(
    db: Session,
    scheme: AcademicScheme,
    subject: Subject,
    data: dict,
    report: dict,
):
    key = f"syllabus-version:{scheme.code}:{subject.code}:{VERSION}"
    version = _find(db, SyllabusVersion, subject_id=subject.id, version=VERSION)
    expected = {
        "academic_scheme_id": scheme.id,
        "source_document_reference": SOURCE_DOCUMENT,
        "source_page_start": data["source_page_start"],
        "source_page_end": data["source_page_end"],
        "source_verification_status": data["source_verification_status"],
        "source_text_imported": False,
    }
    if version is None:
        version = SyllabusVersion(
            id=_stable_id(key),
            subject_id=subject.id,
            version=VERSION,
            verification_status=VerificationStatus.DRAFT,
            active=False,
            **expected,
        )
        db.add(version)
        db.flush()
        _record(report, "syllabus", key, "created")
        return version

    if version.id != _stable_id(key):
        _conflict(report, key, "A manually-created version uses the same natural key; it was left untouched.")
        return None
    differences = [field for field, value in expected.items() if getattr(version, field) != value]
    if differences:
        _conflict(report, key, f"Existing version differs for: {', '.join(differences)}.")
        return None
    _record(report, "syllabus", key, "unchanged")
    return version


def _ensure_unit(db: Session, version: SyllabusVersion, subject: Subject, data: dict, order: int, report: dict):
    key = f"unit:{subject.code}:{VERSION}:{order}"
    unit = _find(db, Unit, syllabus_version_id=version.id, order_index=order)
    expected = {
        "subject_id": subject.id,
        "title": data["title"],
        "duration_hours": data["hours"],
        "source_page_number": data["page"],
        "source_verification_status": data.get("status", "VERIFIED"),
    }
    if unit is None:
        unit = Unit(
            id=_stable_id(key),
            syllabus_version_id=version.id,
            order_index=order,
            verification_status=VerificationStatus.DRAFT,
            active=False,
            **expected,
        )
        db.add(unit)
        db.flush()
        _record(report, "syllabus", key, "created")
        return unit
    if unit.id != _stable_id(key):
        _conflict(report, key, "A manually-created unit occupies this version/order; it was left untouched.")
        return None
    differences = [field for field, value in expected.items() if getattr(unit, field) != value]
    if differences:
        _conflict(report, key, f"Existing unit differs for: {', '.join(differences)}.")
        return None
    _record(report, "syllabus", key, "unchanged")
    return unit


def _ensure_topic(db: Session, unit: Unit, subject: Subject, data: dict, order: int, report: dict):
    key = f"topic:{subject.code}:{VERSION}:{unit.order_index}:{order}"
    topic = _find(db, Topic, unit_id=unit.id, order_index=order)
    expected = {
        "title": data["title"],
        "kind": data.get("kind", "SYLLABUS"),
        "source_page_number": data.get("page", unit.source_page_number),
        "source_verification_status": data.get("status", "VERIFIED"),
    }
    if topic is None:
        topic = Topic(
            id=_stable_id(key),
            unit_id=unit.id,
            order_index=order,
            verification_status=VerificationStatus.DRAFT,
            active=False,
            **expected,
        )
        db.add(topic)
        db.flush()
        _record(report, "syllabus", key, "created")
        return topic
    if topic.id != _stable_id(key):
        _conflict(report, key, "A manually-created topic occupies this unit/order; it was left untouched.")
        return None
    differences = [field for field, value in expected.items() if getattr(topic, field) != value]
    if differences:
        _conflict(report, key, f"Existing topic differs for: {', '.join(differences)}.")
        return None
    _record(report, "syllabus", key, "unchanged")
    return topic


def _ensure_subtopic(
    db: Session,
    topic: Topic,
    subject: Subject,
    data: dict,
    order: int,
    report: dict,
):
    key = f"subtopic:{subject.code}:{VERSION}:{topic.unit_id}:{topic.order_index}:{order}"
    subtopic = _find(db, Subtopic, topic_id=topic.id, order_index=order)
    expected = {
        "title": data["title"],
        "source_page_number": data.get("page", topic.source_page_number),
        "source_verification_status": data.get("status", "VERIFIED"),
    }
    if subtopic is None:
        subtopic = Subtopic(
            id=_stable_id(key),
            topic_id=topic.id,
            order_index=order,
            verification_status=VerificationStatus.DRAFT,
            active=False,
            **expected,
        )
        db.add(subtopic)
        db.flush()
        _record(report, "syllabus", key, "created")
        return subtopic
    if subtopic.id != _stable_id(key):
        _conflict(report, key, "A manually-created subtopic occupies this topic/order; it was left untouched.")
        return None
    differences = [field for field, value in expected.items() if getattr(subtopic, field) != value]
    if differences:
        _conflict(report, key, f"Existing subtopic differs for: {', '.join(differences)}.")
        return None
    _record(report, "syllabus", key, "unchanged")
    return subtopic


def import_semester_iii(db: Session, *, apply: bool = False) -> dict:
    """Create missing catalog and source-linked syllabus rows; never overwrite existing records."""
    validate_import_data()
    report = {
        "mode": "apply" if apply else "dry-run",
        "catalog": defaultdict(int),
        "syllabus": defaultdict(int),
        "records": [],
        "conflicts": [],
    }
    try:
        college = _ensure_identity(
            db,
            College,
            filters={"code": "RVCE"},
            values={"name": "R.V. College of Engineering", "code": "RVCE", "active": True},
            stable_key="college:RVCE",
            report=report,
            record_key="college:RVCE",
        )
        if college is None:
            db.rollback()
            return _finalize_report(report)

        branch = _ensure_identity(
            db,
            Branch,
            filters={"college_id": college.id, "code": "CSE"},
            values={
                "college_id": college.id,
                "name": "Computer Science and Engineering",
                "code": "CSE",
                "active": True,
            },
            stable_key="branch:RVCE:CSE",
            report=report,
            record_key="branch:RVCE:CSE",
        )
        scheme = _ensure_identity(
            db,
            AcademicScheme,
            filters={"college_id": college.id, "code": "2025"},
            values={
                "college_id": college.id,
                "name": "2025 Academic Scheme",
                "code": "2025",
                "active": True,
            },
            stable_key="scheme:RVCE:2025",
            report=report,
            record_key="scheme:RVCE:2025",
        )
        if branch is None or scheme is None:
            db.rollback()
            return _finalize_report(report)

        semester = _ensure_identity(
            db,
            Semester,
            filters={"academic_scheme_id": scheme.id, "number": 3},
            values={
                "academic_scheme_id": scheme.id,
                "number": 3,
                "name": "Semester III",
                "active": True,
            },
            stable_key="semester:RVCE:2025:3",
            report=report,
            record_key="semester:RVCE:2025:3",
        )
        if semester is None:
            db.rollback()
            return _finalize_report(report)

        subjects = {}
        valid_offerings = set()
        for data in SEMESTER_III_SUBJECTS:
            subject = _ensure_subject(db, scheme, semester, data, report)
            if subject is None:
                continue
            subjects[data["code"]] = subject
            if _ensure_offering(db, branch, subject, report):
                valid_offerings.add(data["code"])

        basket = _ensure_basket(db, scheme, semester, branch, report)
        if basket is not None:
            for code in sorted(ELECTIVE_OPTION_CODES):
                subject = subjects.get(code)
                if subject is None or code not in valid_offerings:
                    _conflict(report, f"elective-option:{code}", "Subject or branch offering is unavailable.")
                    continue
                option = db.get(ElectiveOption, (basket.id, subject.id))
                if option is None:
                    db.add(ElectiveOption(basket_id=basket.id, subject_id=subject.id))
                    db.flush()
                    _record(report, "catalog", f"elective-option:{code}", "created")
                else:
                    _record(report, "catalog", f"elective-option:{code}", "unchanged")

        for data in SEMESTER_III_SUBJECTS:
            subject = subjects.get(data["code"])
            if subject is None:
                continue
            version = _ensure_syllabus_version(db, scheme, subject, data, report)
            if version is None:
                continue
            for unit_order, unit_data in enumerate(data["units"], start=1):
                unit = _ensure_unit(db, version, subject, unit_data, unit_order, report)
                if unit is None:
                    continue
                for topic_order, topic_data in enumerate(unit_data["topics"], start=1):
                    topic = _ensure_topic(db, unit, subject, topic_data, topic_order, report)
                    if topic is None:
                        continue
                    for subtopic_order, subtopic_data in enumerate(
                        topic_data.get("subtopics", ()),
                        start=1,
                    ):
                        _ensure_subtopic(
                            db,
                            topic,
                            subject,
                            subtopic_data,
                            subtopic_order,
                            report,
                        )

        if apply:
            db.commit()
        else:
            db.rollback()
        return _finalize_report(report)
    except IntegrityError:
        db.rollback()
        raise


def _finalize_report(report: dict) -> dict:
    report["catalog"] = dict(report["catalog"])
    report["syllabus"] = dict(report["syllabus"])
    return report


def format_import_report(report: dict) -> str:
    import json

    return json.dumps(report, indent=2, sort_keys=True)
