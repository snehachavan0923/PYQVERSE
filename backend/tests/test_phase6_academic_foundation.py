import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes import _require_published_version, _require_student_subject_access
from app.data.semester_iii_2025 import (
    SEMESTER_III_SUBJECTS,
    SOURCE_DOCUMENT,
    SOURCE_SHA256,
    VERSION,
)
from app.database.base import Base
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
from app.services.academic_syllabus_import import import_semester_iii, validate_import_data
from app.services.seed_academic_catalog import _static_dry_run_report


TABLES = [
    College.__table__,
    Branch.__table__,
    AcademicScheme.__table__,
    Semester.__table__,
    Subject.__table__,
    BranchSubjectOffering.__table__,
    ElectiveBasket.__table__,
    ElectiveOption.__table__,
    SyllabusVersion.__table__,
    Unit.__table__,
    Topic.__table__,
    Subtopic.__table__,
]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_source_catalog_covers_only_semester_iii_and_marks_credit_conflict():
    validate_import_data()
    assert {item["code"] for item in SEMESTER_III_SUBJECTS} == {
        "MA231TC", "CV232TA", "ME232TB", "BT232TD", "CS233AI",
        "CS234AI", "CS235AT", "CS236AT", "CS238DL", "MAT149AT",
    }
    bridge = next(item for item in SEMESTER_III_SUBJECTS if item["code"] == "MAT149AT")
    assert bridge["source_verification_status"] == "NEEDS_REVIEW"
    assert bridge["credits"] == 0
    assert "states total credits 2" in bridge["source_notes"]
    lab = next(item for item in SEMESTER_III_SUBJECTS if item["code"] == "CS238DL")
    assert lab["units"] == ()


def test_source_file_and_complete_syllabus_hierarchy_are_pinned():
    root = Path(__file__).resolve().parents[2]
    source = root / "docs" / "source-syllabus" / SOURCE_DOCUMENT
    assert source.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256

    expected_counts = {
        "MA231TC": (5, 5, 44),
        "CV232TA": (5, 5, 49),
        "ME232TB": (5, 11, 61),
        "BT232TD": (5, 6, 50),
        "CS233AI": (5, 14, 77),
        "CS234AI": (5, 11, 64),
        "CS235AT": (5, 9, 46),
        "CS236AT": (5, 7, 39),
        "CS238DL": (0, 0, 0),
        "MAT149AT": (3, 6, 23),
    }
    expected_subjects = {
        "MA231TC": ("Linear Algebra and Probability Theory", "CORE", 4, (3, 1, 0), (45, 30, 0, 45), (5, 6)),
        "CV232TA": ("Environment and Sustainability", "ELECTIVE", 3, (3, 0, 0), (45, 0, 0, 45), (7, 9)),
        "ME232TB": ("Material Science for Engineers", "ELECTIVE", 3, (3, 0, 0), (45, 0, 0, 45), (10, 11)),
        "BT232TD": ("Bioinspired Engineering", "ELECTIVE", 3, (3, 0, 0), (45, 0, 0, 45), (12, 14)),
        "CS233AI": ("Data Structures and Applications", "CORE", 4, (3, 0, 1), (45, 0, 30, 45), (15, 19)),
        "CS234AI": ("Applied Digital Logic Design and Computer Organization", "CORE", 4, (3, 0, 1), (45, 0, 30, 45), (20, 22)),
        "CS235AT": ("Operating Systems", "CORE", 3, (3, 0, 0), (45, 0, 0, 45), (23, 24)),
        "CS236AT": ("Quantum Computing Essentials", "CORE", 3, (3, 0, 0), (45, 0, 0, 45), (25, 27)),
        "CS238DL": ("Applied Design Thinking Lab", "CORE", 1, (0, 0, 1), (0, 0, 30, 0), (28, 29)),
        "MAT149AT": ("Bridge Course Mathematics", "CORE", 0, (2, 0, 0), (30, 0, 0, 30), (30, 30)),
    }
    assert VERSION == "2025-semester-iii-source-v2"
    assert {item["code"] for item in SEMESTER_III_SUBJECTS} == set(expected_counts)
    assert {
        item["code"] for item in SEMESTER_III_SUBJECTS if item["subject_type"] == "ELECTIVE"
    } == {"CV232TA", "ME232TB", "BT232TD"}
    core_credits = sum(
        item["credits"]
        for item in SEMESTER_III_SUBJECTS
        if item["subject_type"] == "CORE"
    )
    one_elective_credit_value = next(
        item["credits"]
        for item in SEMESTER_III_SUBJECTS
        if item["subject_type"] == "ELECTIVE"
    )
    assert core_credits + one_elective_credit_value == 22

    for subject in SEMESTER_III_SUBJECTS:
        title, subject_type, credits, ltp, hours, pages = expected_subjects[subject["code"]]
        assert subject["name"] == title
        assert subject["subject_type"] == subject_type
        assert subject["credits"] == credits
        assert (
            subject["lecture_credits"],
            subject["tutorial_credits"],
            subject["practical_credits"],
        ) == ltp
        assert (
            subject["lecture_hours"],
            subject["tutorial_hours"],
            subject["practical_hours"],
            subject["self_study_hours"],
        ) == hours
        assert (subject["source_page_start"], subject["source_page_end"]) == pages
        topics = [topic for unit in subject["units"] for topic in unit["topics"]]
        subtopics = [
            subtopic
            for topic in topics
            for subtopic in topic.get("subtopics", ())
        ]
        assert (
            len(subject["units"]),
            len(topics),
            len(subtopics),
        ) == expected_counts[subject["code"]]
        assert subject["source_page_start"] <= subject["source_page_end"]
        assert all(
            subject["source_page_start"] <= unit["page"] <= subject["source_page_end"]
            for unit in subject["units"]
        )
        assert all(
            topic["subtopics"]
            for topic in topics
            if topic["kind"] == "SELF_LEARNING"
        )

    assert sum(count[0] for count in expected_counts.values()) == 43
    assert sum(count[1] for count in expected_counts.values()) == 74
    assert sum(count[2] for count in expected_counts.values()) == 453


def test_static_seed_plan_includes_subtopics_without_database_access():
    report = _static_dry_run_report()

    assert report["mode"] == "dry-run"
    assert report["database_touched"] is False
    assert report["planned"] == {
        "academic_hierarchy": 4,
        "subjects": 10,
        "branch_offerings": 10,
        "elective_options": 3,
        "syllabus_versions": 10,
        "units": 43,
        "topics": 74,
        "subtopics": 453,
    }


def test_import_is_idempotent_and_keeps_versions_unpublished(db):
    first = import_semester_iii(db, apply=True)
    second = import_semester_iii(db, apply=True)

    assert first["conflicts"] == []
    assert first["catalog"]["created"] > 0
    assert first["syllabus"]["created"] > 0
    assert second["conflicts"] == []
    assert second["catalog"].get("created", 0) == 0
    assert second["syllabus"].get("created", 0) == 0
    assert db.scalar(select(func.count()).select_from(Subject)) == 10
    assert db.scalar(select(func.count()).select_from(SyllabusVersion)) == 10
    assert db.scalar(select(func.count()).select_from(Unit)) == 43
    assert db.scalar(select(func.count()).select_from(Topic)) == 74
    assert db.scalar(select(func.count()).select_from(Subtopic)) == 453

    versions = db.scalars(select(SyllabusVersion)).all()
    assert all(not version.active for version in versions)
    assert all(version.verification_status == VerificationStatus.DRAFT for version in versions)
    assert all(version.source_text_imported is False for version in versions)
    assert all(version.source_document_reference == "Syllabus_Copy.pdf" for version in versions)
    assert all(version.version == VERSION for version in versions)

    option_rows = db.execute(
        select(ElectiveOption, Subject)
        .join(Subject, Subject.id == ElectiveOption.subject_id)
    ).all()
    assert {subject.code for _, subject in option_rows} == {"CV232TA", "ME232TB", "BT232TD"}
    assert all(subject.course_category == "Professional Core Course" for _, subject in option_rows)

    ds = db.scalar(select(Subject).where(Subject.code == "CS233AI"))
    units = db.scalars(
        select(Unit).where(Unit.subject_id == ds.id).order_by(Unit.order_index)
    ).all()
    assert [unit.order_index for unit in units] == [1, 2, 3, 4, 5]
    assert all(unit.source_page_number is not None for unit in units)
    assert all(not unit.active for unit in units)
    self_learning = db.scalars(select(Topic).where(Topic.kind == "SELF_LEARNING")).all()
    assert len(self_learning) == 5
    assert all(
        db.scalar(select(func.count()).select_from(Subtopic).where(Subtopic.topic_id == topic.id)) > 0
        for topic in self_learning
    )

    for data in SEMESTER_III_SUBJECTS:
        subject = db.scalar(select(Subject).where(Subject.code == data["code"]))
        assert subject is not None
        units = db.scalars(
            select(Unit).where(Unit.subject_id == subject.id).order_by(Unit.order_index)
        ).all()
        assert [unit.order_index for unit in units] == list(range(1, len(data["units"]) + 1))
        assert [unit.title for unit in units] == [unit["title"] for unit in data["units"]]
        assert all(
            data["source_page_start"] <= unit.source_page_number <= data["source_page_end"]
            for unit in units
        )
        assert all(
            unit.source_verification_status == expected_unit.get("status", "VERIFIED")
            for unit, expected_unit in zip(units, data["units"], strict=True)
        )
        for unit, expected_unit in zip(units, data["units"], strict=True):
            topics = db.scalars(
                select(Topic).where(Topic.unit_id == unit.id).order_by(Topic.order_index)
            ).all()
            assert [topic.order_index for topic in topics] == list(
                range(1, len(expected_unit["topics"]) + 1)
            )
            assert [topic.title for topic in topics] == [
                topic["title"] for topic in expected_unit["topics"]
            ]
            assert all(
                topic.source_page_number == expected_unit["page"]
                and topic.source_verification_status == expected_topic.get("status", "VERIFIED")
                for topic, expected_topic in zip(
                    topics,
                    expected_unit["topics"],
                    strict=True,
                )
            )
            for topic, expected_topic in zip(topics, expected_unit["topics"], strict=True):
                subtopics = db.scalars(
                    select(Subtopic)
                    .where(Subtopic.topic_id == topic.id)
                    .order_by(Subtopic.order_index)
                ).all()
                assert [subtopic.order_index for subtopic in subtopics] == list(
                    range(1, len(expected_topic.get("subtopics", ())) + 1)
                )
                assert [subtopic.title for subtopic in subtopics] == [
                    subtopic["title"]
                    for subtopic in expected_topic.get("subtopics", ())
                ]
                assert all(
                    subtopic.source_page_number == expected_unit["page"]
                    and subtopic.source_verification_status == "VERIFIED"
                    for subtopic in subtopics
                )


def test_import_enriches_empty_metadata_but_does_not_overwrite_manual_values(db):
    import_semester_iii(db, apply=True)
    subject = db.scalar(select(Subject).where(Subject.code == "MA231TC"))
    subject.name = "Manually maintained title"
    db.commit()

    report = import_semester_iii(db, apply=True)

    assert subject.name == "Manually maintained title"
    assert any("Existing values differ" in item["detail"] for item in report["conflicts"])


def test_import_does_not_overwrite_manually_edited_syllabus_content(db):
    import_semester_iii(db, apply=True)
    subject = db.scalar(select(Subject).where(Subject.code == "CS233AI"))
    unit = db.scalar(
        select(Unit).where(
            Unit.subject_id == subject.id,
            Unit.order_index == 1,
        )
    )
    topic = db.scalar(
        select(Topic).where(
            Topic.unit_id == unit.id,
            Topic.order_index == 1,
        )
    )
    topic.title = "Manually managed topic"
    db.commit()

    report = import_semester_iii(db, apply=True)

    assert topic.title == "Manually managed topic"
    assert any("Existing topic differs" in item["detail"] for item in report["conflicts"])


def test_dry_run_rolls_back_all_rows(db):
    report = import_semester_iii(db, apply=False)

    assert report["mode"] == "dry-run"
    assert db.scalar(select(func.count()).select_from(Subject)) == 0
    assert db.scalar(select(func.count()).select_from(SyllabusVersion)) == 0


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class AccessDB:
    def __init__(self, profile, enrollment, offering):
        self.results = [profile, enrollment]
        self.offering = offering
        self.statements = []

    def scalars(self, statement):
        self.statements.append(statement)
        return ScalarResult(self.results.pop(0))

    def get(self, model, key):
        if model is BranchSubjectOffering:
            return self.offering
        return None


def test_student_hierarchy_reads_require_matching_active_enrollment_and_branch_offering():
    student_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    branch_id = uuid.uuid4()
    subject = type(
        "SubjectStub",
        (),
        {
            "id": uuid.uuid4(),
            "active": True,
            "academic_scheme_id": uuid.uuid4(),
            "semester_id": uuid.uuid4(),
        },
    )()
    profile = type(
        "ProfileStub",
        (),
        {
            "id": profile_id,
            "branch_id": branch_id,
            "academic_scheme_id": subject.academic_scheme_id,
            "current_semester_id": subject.semester_id,
            "profile_completed": True,
        },
    )()
    enrollment = type("EnrollmentStub", (), {"id": uuid.uuid4()})()
    student = type("UserStub", (), {"id": student_id})()

    _require_student_subject_access(
        AccessDB(profile, enrollment, type("OfferingStub", (), {"active": True})()),
        student,
        subject,
    )

    with pytest.raises(HTTPException) as exc:
        _require_student_subject_access(AccessDB(profile, enrollment, None), student, subject)
    assert exc.value.status_code == 403

    mismatch = type(
        "ProfileStub",
        (),
        {
            "id": profile_id,
            "branch_id": branch_id,
            "academic_scheme_id": subject.academic_scheme_id,
            "current_semester_id": uuid.uuid4(),
            "profile_completed": True,
        },
    )()
    with pytest.raises(HTTPException) as exc:
        _require_student_subject_access(
            AccessDB(mismatch, enrollment, type("OfferingStub", (), {"active": True})()),
            student,
            subject,
        )
    assert exc.value.status_code == 403


def test_unpublished_or_unverified_units_are_not_returned():
    unit = type(
        "UnitStub",
        (),
        {
            "id": uuid.uuid4(),
            "subject_id": uuid.uuid4(),
            "syllabus_version_id": uuid.uuid4(),
            "active": True,
            "verification_status": VerificationStatus.VERIFIED,
            "source_verification_status": "VERIFIED",
        },
    )()

    class PublishedDB:
        def __init__(self, version_id):
            self.version_id = version_id
            self.statement = None

        def scalars(self, statement):
            self.statement = statement
            return ScalarResult(self.version_id)

    published_db = PublishedDB(unit.syllabus_version_id)
    _require_published_version(published_db, unit)
    sql = str(published_db.statement)
    assert "syllabus_versions.active" in sql
    assert "syllabus_versions.verification_status" in sql
    assert "syllabus_versions.source_verification_status" in sql

    with pytest.raises(HTTPException) as exc:
        _require_published_version(PublishedDB(None), unit)
    assert exc.value.status_code == 404


def test_scheme_separation_and_version_scoped_content_ordering(db):
    import_semester_iii(db, apply=True)
    original = db.scalar(select(Subject).where(Subject.code == "MA231TC"))
    scheme_2025 = db.get(AcademicScheme, original.academic_scheme_id)
    scheme_2024 = AcademicScheme(
        id=uuid.uuid4(),
        college_id=scheme_2025.college_id,
        name="2024 Academic Scheme",
        code="2024",
        active=True,
    )
    db.add(scheme_2024)
    db.flush()
    semester_2024 = Semester(
        id=uuid.uuid4(),
        academic_scheme_id=scheme_2024.id,
        number=3,
        name="Semester III",
        active=True,
    )
    db.add(semester_2024)
    db.add(
        Subject(
            id=uuid.uuid4(),
            academic_scheme_id=scheme_2024.id,
            semester_id=semester_2024.id,
            code=original.code,
            name=original.name,
            subject_type="CORE",
            active=True,
        )
    )
    db.commit()
    assert db.scalar(select(func.count()).select_from(Subject).where(Subject.code == "MA231TC")) == 2

    version_2025 = db.scalar(
        select(SyllabusVersion).where(SyllabusVersion.subject_id == original.id)
    )
    version_2 = SyllabusVersion(
        id=uuid.uuid4(),
        academic_scheme_id=original.academic_scheme_id,
        subject_id=original.id,
        version="2025-v2",
        verification_status=VerificationStatus.DRAFT,
        active=False,
    )
    db.add(version_2)
    db.flush()
    unit_2 = Unit(
        id=uuid.uuid4(),
        subject_id=original.id,
        syllabus_version_id=version_2.id,
        title="Unit I",
        order_index=1,
        verification_status=VerificationStatus.DRAFT,
        active=False,
    )
    db.add(unit_2)
    db.flush()
    assert version_2025 is not None
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Unit(
                    id=uuid.uuid4(),
                    subject_id=original.id,
                    syllabus_version_id=version_2.id,
                    title="Duplicate order",
                    order_index=1,
                    verification_status=VerificationStatus.DRAFT,
                    active=False,
                )
            )
            db.flush()

    topic = db.scalar(select(Topic).where(Topic.unit_id == unit_2.id))
    if topic is None:
        topic = Topic(
            id=uuid.uuid4(),
            unit_id=unit_2.id,
            title="Topic",
            kind="SYLLABUS",
            order_index=1,
            verification_status=VerificationStatus.DRAFT,
            active=False,
        )
        db.add(topic)
        db.flush()
    db.add(
        Subtopic(
            id=uuid.uuid4(),
            topic_id=topic.id,
            title="Subtopic",
            order_index=1,
            verification_status=VerificationStatus.DRAFT,
            active=False,
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Subtopic(
                    id=uuid.uuid4(),
                    topic_id=topic.id,
                    title="Duplicate subtopic order",
                    order_index=1,
                    verification_status=VerificationStatus.DRAFT,
                    active=False,
                )
            )
            db.flush()


def test_hierarchy_reads_require_student_and_offering_management_requires_admin():
    from app.api.admin_academic_routes import router as admin_router
    from app.api.deps import require_admin, require_student
    from app.api.routes import router as public_router

    for path in (
        "/api/v1/subjects/{subject_id}/units",
        "/api/v1/units/{unit_id}/topics",
        "/api/v1/topics/{topic_id}/subtopics",
    ):
        route = next(route for route in public_router.routes if route.path == path)
        assert require_student in {dependency.call for dependency in route.dependant.dependencies}

    offering_route = next(
        route for route in admin_router.routes if route.path == "/api/v1/admin/academic/offerings"
        and "POST" in route.methods
    )
    assert require_admin in {
        dependency.call for dependency in offering_route.dependant.dependencies
    }
