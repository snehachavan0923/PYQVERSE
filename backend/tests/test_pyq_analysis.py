"""Comprehensive test suite for the Automated AI-Powered PYQ Analysis Engine."""

import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import analysis_routes
from app.api.deps import get_current_user, require_admin
from app.database.connection import get_db
from app.main import app
from app.models.academic import StudentProfile, StudentSubjectEnrollment, Subject
from app.models.analysis import (
    AnalysisJob,
    AnalysisJobStatus,
    QuestionClassification,
    QuestionSimilarity,
    RepeatCategory,
    SubjectAnalysisSummary,
)
from app.models.document import ExamType, QuestionPaper, UploadedDocument
from app.models.question import Question, QuestionTopicMap
from app.models.syllabus import Topic, Unit, VerificationStatus
from app.models.user import AccountStatus, UserRole
from app.services.ai_provider import (
    RuleAndKeywordAIProvider,
    calculate_jaccard_similarity,
    get_ai_provider,
    tokenize_clean,
)
from app.services.pdf_extraction import (
    extract_marks_from_text,
    extract_questions_from_pdf,
    parse_page_questions,
)
from app.services.pyq_statistics import calculate_topic_priority_score


def _admin_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Faculty Admin",
        email="admin@rvce.edu.in",
        role=UserRole.ADMIN_FACULTY,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


def _student_user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Engineering Student",
        email="student@rvce.edu.in",
        role=UserRole.STUDENT,
        account_status=AccountStatus.ACTIVE,
        email_verified=True,
    )


# ---------------------------------------------------------------------------
# 1. PDF Extraction Engine Tests
# ---------------------------------------------------------------------------
def test_extract_marks_from_text():
    text1, marks1 = extract_marks_from_text("Explain the 8086 register set with a diagram. [10 Marks]")
    assert marks1 == 10
    assert "Explain the 8086 register set" in text1

    text2, marks2 = extract_marks_from_text("Differentiate SRAM vs DRAM (5M)")
    assert marks2 == 5

    text3, marks3 = extract_marks_from_text("Write an algorithm for binary search.")
    assert marks3 is None


def test_parse_page_questions_structured():
    sample_text = """
    MODULE - 1
    1. a) Explain memory hierarchy with cache mapping techniques. [10 Marks]
    b) Compare associative mapping and direct mapping. (6 marks)

    2. a) What is virtual memory? Explain paging mechanism. [08]
    """
    questions, section = parse_page_questions(sample_text, 1, None)
    assert len(questions) == 3
    assert questions[0].question_number == "1.a"
    assert questions[0].marks == 10
    assert "Explain memory hierarchy" in questions[0].extracted_text
    assert questions[0].section == "MODULE - 1"

    assert questions[1].question_number == "1.b"
    assert questions[1].marks == 6

    assert questions[2].question_number == "2.a"
    assert questions[2].marks == 8


# ---------------------------------------------------------------------------
# 2. AI Question Classification & Heuristics Tests
# ---------------------------------------------------------------------------
def test_ai_provider_classification():
    provider = RuleAndKeywordAIProvider()

    syllabus_units = [
        {
            "order_index": 1,
            "title": "Microprocessor Architecture and 8086",
            "topics": [
                {
                    "id": uuid.uuid4(),
                    "title": "8086 Architecture and Registers",
                    "order_index": 1,
                    "subtopics": [{"id": uuid.uuid4(), "title": "General Purpose Registers"}],
                },
                {
                    "id": uuid.uuid4(),
                    "title": "Memory Segmentation",
                    "order_index": 2,
                    "subtopics": [],
                },
            ],
        },
        {
            "order_index": 2,
            "title": "Instruction Set and Assembly Programming",
            "topics": [
                {
                    "id": uuid.uuid4(),
                    "title": "Assembly Programming and Addressing Modes",
                    "order_index": 1,
                    "subtopics": [],
                }
            ],
        },
    ]

    # Question on unit 1
    res = provider.classify_question(
        question_text="Explain 8086 architecture and registers with a neat schematic diagram.",
        marks=10,
        syllabus_units=syllabus_units,
    )
    assert res.unit_number == 1
    assert "8086" in (res.suggested_topic_title or "")
    assert res.bloom_taxonomy in ["UNDERSTAND", "ANALYZE", "REMEMBER"]
    assert res.question_type in ["DIAGRAM", "THEORY"]
    assert res.difficulty in ["MEDIUM", "HARD"]
    assert res.confidence >= 0.60


def test_ai_question_repetition_detection():
    provider = RuleAndKeywordAIProvider()

    # Exact match
    q1 = "Explain the architecture of 8086 microprocessor with neat diagram."
    q2 = "Explain the architecture of 8086 microprocessor with neat diagram."
    comp_exact = provider.compare_questions(q1, q2)
    assert comp_exact.repeat_category == RepeatCategory.EXACT_REPEAT
    assert comp_exact.similarity_score >= 0.95

    # Reworded repeat
    q3 = "With a neat sketch, explain 8086 microprocessor architecture."
    comp_reworded = provider.compare_questions(q1, q3)
    assert comp_reworded.repeat_category in [RepeatCategory.EXACT_REPEAT, RepeatCategory.REWORDED_REPEAT]
    assert comp_reworded.similarity_score >= 0.60

    # Different topic
    q4 = "Write a quicksort algorithm in C."
    comp_diff = provider.compare_questions(q1, q4)
    assert comp_diff.repeat_category in [RepeatCategory.RELATED_CONCEPT, RepeatCategory.SAME_TOPIC_DIFFERENT_QUESTION]
    assert comp_diff.similarity_score < 0.40


# ---------------------------------------------------------------------------
# 3. Statistical Priority Scoring Tests
# ---------------------------------------------------------------------------
def test_topic_priority_score_calculation():
    # High frequency, high marks, recent appearance, 2 repeats
    score_high, cat_high, breakdown = calculate_topic_priority_score(
        frequency=5,
        total_marks=45,
        max_frequency=5,
        max_marks=45,
        appeared_recently=True,
        repeat_count=2,
        total_papers=4,
    )
    assert score_high >= 80.0
    assert cat_high == "VERY_HIGH"
    assert breakdown["frequency_score"] == 40.0
    assert breakdown["marks_score"] == 30.0
    assert breakdown["recency_score"] == 20.0
    assert breakdown["repeat_bonus"] == 10.0

    # Low frequency topic
    score_low, cat_low, _ = calculate_topic_priority_score(
        frequency=1,
        total_marks=5,
        max_frequency=5,
        max_marks=45,
        appeared_recently=False,
        repeat_count=0,
        total_papers=4,
    )
    assert score_low < 35.0
    assert cat_low == "LOW"

    # Insufficient historical data (< 2 papers)
    score_insuf, cat_insuf, _ = calculate_topic_priority_score(
        frequency=1,
        total_marks=10,
        max_frequency=1,
        max_marks=10,
        appeared_recently=True,
        repeat_count=0,
        total_papers=1,
    )
    assert cat_insuf == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# 4. API Endpoints Integration Tests
# ---------------------------------------------------------------------------
class MockAnalysisDB:
    def __init__(self, entities=None):
        self.entities = entities or {}
        self.committed = False

    def get(self, model, key):
        return self.entities.get((model, key))

    def scalar(self, query):
        q_str = str(query)
        if "count" in q_str.lower():
            return 1
        for (m, _k), obj in self.entities.items():
            if getattr(m, "__tablename__", "") in q_str:
                return obj
        return None

    def scalars(self, query):
        q_str = str(query)
        items = [
            obj for (m, _k), obj in self.entities.items()
            if getattr(m, "__tablename__", "") in q_str
        ]
        return SimpleNamespace(all=lambda: list(items), first=lambda: items[0] if items else None)

    def execute(self, query):
        items = []
        for (m, _k), obj in self.entities.items():
            items.append((obj,))
        return SimpleNamespace(all=lambda: items)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass

    def add(self, obj):
        pass


def test_admin_correct_question_approve():
    client = TestClient(app)
    admin = _admin_user()
    app.dependency_overrides[require_admin] = lambda: admin

    q_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    q = Question(
        id=q_id,
        document_id=doc_id,
        question_number="1.a",
        extracted_text="Explain 8086 flags.",
        marks=6,
        verification_status=VerificationStatus.DRAFT,
    )
    cl = QuestionClassification(
        id=uuid.uuid4(),
        question_id=q_id,
        main_topic="Registers",
        confidence=0.55,
        provisional=True,
    )
    doc = UploadedDocument(
        id=doc_id,
        original_filename="paper.pdf",
        file_type="pdf",
        file_size=1000,
        storage_path="pyq/test.pdf",
        subject_id=sub_id,
        exam_type=ExamType.SEE,
        uploaded_by=admin.id,
    )

    db = MockAnalysisDB(entities={
        (Question, q_id): q,
        (QuestionClassification, cl.id): cl,
        (UploadedDocument, doc_id): doc,
    })
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.patch(
            f"/api/v1/admin/analysis/questions/{q_id}",
            json={
                "main_topic": "8086 Flag Register",
                "subtopic": "Status & Control Flags",
                "unit_number": 1,
                "marks": 8,
                "action": "APPROVE",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["verification_status"] == "VERIFIED"
        assert q.verification_status == VerificationStatus.VERIFIED
        assert cl.provisional is False
        assert cl.confidence == 1.0
        assert q.marks == 8
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


def test_admin_retry_analysis_job(monkeypatch):
    client = TestClient(app)
    admin = _admin_user()
    app.dependency_overrides[require_admin] = lambda: admin

    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        question_paper_id=uuid.uuid4(),
        uploaded_document_id=uuid.uuid4(),
        status=AnalysisJobStatus.FAILED,
        stage="Failed during OCR",
        progress_percent=20,
    )

    db = MockAnalysisDB(entities={(AnalysisJob, job_id): job})
    app.dependency_overrides[get_db] = lambda: db

    retried_jobs = []
    monkeypatch.setattr(analysis_routes, "run_pyq_analysis_job", lambda j_id: retried_jobs.append(j_id))

    try:
        response = client.post(f"/api/v1/admin/analysis/jobs/{job_id}/retry")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING"
        assert job.status == AnalysisJobStatus.PENDING
        assert job.progress_percent == 0
        assert job_id in retried_jobs
    finally:
        app.dependency_overrides.pop(require_admin, None)
        app.dependency_overrides.pop(get_db, None)


def test_student_get_subject_analysis():
    client = TestClient(app)
    student = _student_user()
    app.dependency_overrides[get_current_user] = lambda: student

    sub_id = uuid.uuid4()
    subject = Subject(
        id=sub_id,
        code="22CS52",
        name="Computer Architecture",
        active=True,
    )
    summary = SubjectAnalysisSummary(
        id=uuid.uuid4(),
        subject_id=sub_id,
        total_papers=3,
        total_questions=24,
        coverage_score=75.0,
        unit_stats=[
            {"unit_number": 1, "title": "Basics", "question_count": 8, "total_marks": 50, "marks_percentage": 33.3}
        ],
        topic_insights=[
            {
                "topic_title": "Pipelining",
                "unit_number": 1,
                "frequency": 4,
                "total_marks": 32,
                "priority_score": 88.5,
                "priority_category": "VERY_HIGH",
            }
        ],
        repeated_question_clusters=[],
        recommendations={"study_first": [], "insufficient_data": False, "syllabus_status": "AVAILABLE"},
    )

    profile = StudentProfile(
        id=uuid.uuid4(),
        user_id=student.id,
        student_name=student.full_name,
        profile_completed=True,
    )
    enrollment = StudentSubjectEnrollment(
        id=uuid.uuid4(),
        student_profile_id=profile.id,
        subject_id=sub_id,
        semester_id=uuid.uuid4(),
        academic_scheme_id=uuid.uuid4(),
        active=True,
    )
    db = MockAnalysisDB(entities={
        (StudentProfile, profile.id): profile,
        (StudentSubjectEnrollment, enrollment.id): enrollment,
        (Subject, sub_id): subject,
        (SubjectAnalysisSummary, summary.id): summary,
    })
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.get(f"/api/v1/student/analysis/{sub_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["subject_code"] == "22CS52"
        assert data["total_papers"] == 3
        assert data["total_questions"] == 24
        assert data["coverage_score"] == 75.0
        assert len(data["topic_insights"]) == 1
        assert data["topic_insights"][0]["priority_category"] == "VERY_HIGH"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
