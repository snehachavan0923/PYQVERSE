"""Student-facing PYQ learning, bookmark, and topic progress APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_student
from app.database.connection import get_db
from app.models.academic import StudentSubjectEnrollment, Subject
from app.models.analysis import (
    AnalysisJob,
    AnalysisJobStatus,
    QuestionClassification,
    QuestionSimilarity,
    SubjectAnalysisSummary,
)
from app.models.document import QuestionPaper, UploadedDocument
from app.models.progress import PyqQuestionBookmark, StudentTopicLearning
from app.models.question import Question
from app.models.resource import LearningResource
from app.models.syllabus import Unit, VerificationStatus
from app.models.user import User
from app.services.pyq_statistics import compute_subject_analysis, slugify_topic_key
from app.services.student_access import enrolled_subject_ids, get_student_profile, require_subject_access

router = APIRouter(tags=["student-learning"])

LEARNING_STATUSES = {"NOT_STARTED", "LEARNING", "LEARNED", "NEEDS_REVISION"}


class TopicProgressRequest(BaseModel):
    status: str = Field(..., description="NOT_STARTED, LEARNING, LEARNED, or NEEDS_REVISION")
    topic_title: Optional[str] = None
    explanation: Optional[str] = None


def _paper_ref(paper: QuestionPaper, document: UploadedDocument) -> Dict[str, Any]:
    return {
        "paper_id": str(paper.id),
        "document_id": str(document.id),
        "title": paper.title or document.title or document.original_filename,
        "original_filename": document.original_filename,
        "exam_type": paper.exam_type.value if paper.exam_type else None,
        "examination_year": paper.examination_year,
        "cie_number": paper.cie_number,
    }


def _question_context(
    db: Session, question: Question
) -> tuple[UploadedDocument, QuestionPaper, Subject]:
    document = db.get(UploadedDocument, question.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    paper = db.scalar(
        select(QuestionPaper).where(QuestionPaper.uploaded_document_id == document.id)
    )
    if paper is None:
        raise HTTPException(status_code=404, detail="Question paper not found")
    subject = db.get(Subject, paper.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return document, paper, subject


def _question_payload(
    db: Session,
    question: Question,
    document: UploadedDocument,
    paper: QuestionPaper,
    subject: Subject,
    profile_id: uuid.UUID,
    classification: Optional[QuestionClassification] = None,
) -> Dict[str, Any]:
    if classification is None:
        classification = db.scalar(
            select(QuestionClassification).where(
                QuestionClassification.question_id == question.id
            )
        )
    bookmarked = (
        db.scalar(
            select(PyqQuestionBookmark.id).where(
                PyqQuestionBookmark.student_profile_id == profile_id,
                PyqQuestionBookmark.question_id == question.id,
            )
        )
        is not None
    )
    repeats = db.scalars(
        select(QuestionSimilarity).where(
            (QuestionSimilarity.source_question_id == question.id)
            | (QuestionSimilarity.target_question_id == question.id)
        )
    ).all()
    return {
        "id": str(question.id),
        "question_number": question.question_number,
        "sequence": question.sequence,
        "extracted_text": question.extracted_text,
        "marks": question.marks,
        "original_page_number": question.original_page_number,
        "verification_status": question.verification_status.value,
        "bookmarked": bookmarked,
        "paper": _paper_ref(paper, document),
        "subject": {
            "id": str(subject.id),
            "code": subject.code,
            "name": subject.name,
        },
        "classification": {
            "main_topic": classification.main_topic if classification else None,
            "subtopic": classification.subtopic if classification else None,
            "related_concepts": classification.related_concepts if classification else [],
            "question_type": classification.question_type if classification else None,
            "difficulty": classification.difficulty if classification else None,
            "bloom_taxonomy": classification.bloom_taxonomy if classification else None,
            "unit_number": classification.unit_number if classification else None,
            "suggested_unit_title": classification.suggested_unit_title if classification else None,
            "suggested_topic_title": classification.suggested_topic_title if classification else None,
            "confidence": classification.confidence if classification else None,
            "explanation": classification.explanation if classification else None,
            "provisional": classification.provisional if classification else False,
        }
        if classification
        else None,
        "repeat_count": len(repeats),
        "max_similarity": max((row.similarity_score for row in repeats), default=None),
    }


def _get_summary(db: Session, subject_id: uuid.UUID) -> SubjectAnalysisSummary:
    summary = db.scalar(
        select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
    )
    if summary is None:
        summary = compute_subject_analysis(db, subject_id)
    return summary


def _topic_learning_map(
    db: Session, profile_id: uuid.UUID, subject_id: uuid.UUID
) -> Dict[str, StudentTopicLearning]:
    rows = db.scalars(
        select(StudentTopicLearning).where(
            StudentTopicLearning.student_profile_id == profile_id,
            StudentTopicLearning.subject_id == subject_id,
        )
    ).all()
    return {row.topic_key: row for row in rows}


def _resource_payload(resource: LearningResource, unit: Optional[Unit]) -> Dict[str, Any]:
    return {
        "id": str(resource.id),
        "title": resource.title,
        "description": resource.description,
        "resource_type": resource.resource_type,
        "resource_source": resource.resource_source,
        "external_url": resource.external_url,
        "link_title": resource.link_title,
        "original_filename": resource.original_filename,
        "file_type": resource.file_type,
        "file_size": resource.file_size,
        "unit_id": str(resource.unit_id) if resource.unit_id else None,
        "unit_title": unit.title if unit else None,
        "uploaded_at": resource.uploaded_at.isoformat() if resource.uploaded_at else None,
    }


def _topic_resources(
    db: Session, subject_id: uuid.UUID, unit_number: Optional[int]
) -> List[Dict[str, Any]]:
    if unit_number is None:
        return []
    unit = db.scalar(
        select(Unit).where(
            Unit.subject_id == subject_id,
            Unit.order_index == unit_number,
            Unit.active.is_(True),
        )
    )
    if unit is None:
        return []
    rows = db.scalars(
        select(LearningResource)
        .where(
            LearningResource.subject_id == subject_id,
            LearningResource.unit_id == unit.id,
            LearningResource.active.is_(True),
            LearningResource.verification_status == VerificationStatus.VERIFIED,
        )
        .order_by(desc(LearningResource.uploaded_at))
    ).all()
    return [_resource_payload(row, unit) for row in rows]


@router.get("/api/v1/student/learning/overview")
def get_learning_overview(
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    """Dashboard overview across the student's enrolled subjects."""
    profile = get_student_profile(db, student)
    subject_ids = enrolled_subject_ids(db, profile)
    if not subject_ids:
        return {
            "subjects": [],
            "totals": {
                "subjects_with_pyqs": 0,
                "questions_analysed": 0,
                "topics_discovered": 0,
                "bookmarked_questions": 0,
                "topics_learned": 0,
                "topics_needing_revision": 0,
            },
        }

    subjects = db.scalars(
        select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.code)
    ).all()

    summaries = {
        row.subject_id: row
        for row in db.scalars(
            select(SubjectAnalysisSummary).where(
                SubjectAnalysisSummary.subject_id.in_(subject_ids)
            )
        ).all()
    }
    paper_counts = dict(
        db.execute(
            select(QuestionPaper.subject_id, func.count(QuestionPaper.id))
            .where(QuestionPaper.subject_id.in_(subject_ids))
            .group_by(QuestionPaper.subject_id)
        ).all()
    )
    question_counts = dict(
        db.execute(
            select(UploadedDocument.subject_id, func.count(Question.id))
            .join(Question, Question.document_id == UploadedDocument.id)
            .where(
                UploadedDocument.subject_id.in_(subject_ids),
                UploadedDocument.active.is_(True),
            )
            .group_by(UploadedDocument.subject_id)
        ).all()
    )
    bookmark_counts = dict(
        db.execute(
            select(UploadedDocument.subject_id, func.count(PyqQuestionBookmark.id))
            .join(Question, Question.document_id == UploadedDocument.id)
            .join(
                PyqQuestionBookmark,
                PyqQuestionBookmark.question_id == Question.id,
            )
            .where(
                PyqQuestionBookmark.student_profile_id == profile.id,
                UploadedDocument.subject_id.in_(subject_ids),
            )
            .group_by(UploadedDocument.subject_id)
        ).all()
    )

    progress_rows = db.scalars(
        select(StudentTopicLearning).where(
            StudentTopicLearning.student_profile_id == profile.id,
            StudentTopicLearning.subject_id.in_(subject_ids),
        )
    ).all()
    progress_by_subject: Dict[uuid.UUID, List[StudentTopicLearning]] = {}
    for row in progress_rows:
        progress_by_subject.setdefault(row.subject_id, []).append(row)

    items = []
    totals = {
        "subjects_with_pyqs": 0,
        "questions_analysed": 0,
        "topics_discovered": 0,
        "bookmarked_questions": 0,
        "topics_learned": 0,
        "topics_needing_revision": 0,
    }
    for subject in subjects:
        summary = summaries.get(subject.id)
        topic_insights = summary.topic_insights if summary else []
        progress = progress_by_subject.get(subject.id, [])
        learned = sum(1 for row in progress if row.status == "LEARNED")
        needs_revision = sum(1 for row in progress if row.status == "NEEDS_REVISION")
        questions = int(question_counts.get(subject.id, 0) or 0)
        papers = int(paper_counts.get(subject.id, 0) or 0)
        bookmarks = int(bookmark_counts.get(subject.id, 0) or 0)

        if questions:
            totals["subjects_with_pyqs"] += 1
        totals["questions_analysed"] += questions
        totals["topics_discovered"] += len(topic_insights)
        totals["bookmarked_questions"] += bookmarks
        totals["topics_learned"] += learned
        totals["topics_needing_revision"] += needs_revision

        top_topic = topic_insights[0] if topic_insights else None
        items.append(
            {
                "subject_id": str(subject.id),
                "subject_code": subject.code,
                "subject_name": subject.name,
                "papers_count": papers,
                "questions_analysed": questions,
                "topics_discovered": len(topic_insights),
                "bookmarked_questions": bookmarks,
                "topics_learned": learned,
                "topics_needing_revision": needs_revision,
                "syllabus_status": (summary.recommendations or {}).get("syllabus_status", "PENDING")
                if summary
                else "PENDING",
                "top_priority_topic": top_topic,
                "has_pyqs": questions > 0,
            }
        )

    return {"subjects": items, "totals": totals}


@router.get("/api/v1/student/subjects/{subject_id}/topics")
def list_student_topics(
    subject_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    """List discovered topics with priority and the student's own learning status."""
    profile, subject = require_subject_access(db, student, subject_id)
    summary = _get_summary(db, subject.id)
    learning = _topic_learning_map(db, profile.id, subject.id)

    items = []
    for insight in summary.topic_insights or []:
        key = insight.get("topic_key") or slugify_topic_key(insight.get("topic_title", ""))
        progress = learning.get(key)
        items.append(
            {
                **insight,
                "topic_key": key,
                "learning_status": progress.status if progress else "NOT_STARTED",
                "learning_explanation": progress.explanation if progress else None,
                "learning_updated_at": progress.updated_at.isoformat()
                if progress and progress.updated_at
                else None,
            }
        )

    return {
        "subject_id": str(subject.id),
        "subject_code": subject.code,
        "subject_name": subject.name,
        "syllabus_status": (summary.recommendations or {}).get("syllabus_status", "PENDING"),
        "items": items,
    }


@router.get("/api/v1/student/subjects/{subject_id}/topics/{topic_key}")
def get_student_topic_detail(
    subject_id: uuid.UUID,
    topic_key: str,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile, subject = require_subject_access(db, student, subject_id)
    summary = _get_summary(db, subject.id)
    insight = next(
        (
            item
            for item in (summary.topic_insights or [])
            if (item.get("topic_key") or slugify_topic_key(item.get("topic_title", ""))) == topic_key
        ),
        None,
    )
    if insight is None:
        raise HTTPException(status_code=404, detail="Topic not found in analysed PYQs")

    progress = db.scalar(
        select(StudentTopicLearning).where(
            StudentTopicLearning.student_profile_id == profile.id,
            StudentTopicLearning.subject_id == subject.id,
            StudentTopicLearning.topic_key == topic_key,
        )
    )
    resources = _topic_resources(db, subject.id, insight.get("unit_number"))

    related_questions = []
    for sample in insight.get("sample_questions", [])[:5]:
        try:
            sample_id = uuid.UUID(str(sample.get("question_id")))
        except (TypeError, ValueError):
            continue
        question = db.get(Question, sample_id)
        if not question:
            continue
        document, paper, question_subject = _question_context(db, question)
        related_questions.append(
            _question_payload(
                db, question, document, paper, question_subject, profile.id
            )
        )

    return {
        "subject_id": str(subject.id),
        "subject_code": subject.code,
        "subject_name": subject.name,
        "topic": {
            **insight,
            "topic_key": topic_key,
            "learning_status": progress.status if progress else "NOT_STARTED",
            "learning_explanation": progress.explanation if progress else None,
            "learning_updated_at": progress.updated_at.isoformat()
            if progress and progress.updated_at
            else None,
        },
        "resources": resources,
        "related_questions": related_questions,
    }


@router.patch("/api/v1/student/subjects/{subject_id}/topics/{topic_key}")
def update_topic_progress(
    subject_id: uuid.UUID,
    topic_key: str,
    payload: TopicProgressRequest,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile, subject = require_subject_access(db, student, subject_id)
    status = payload.status.strip().upper()
    if status not in LEARNING_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="status must be one of NOT_STARTED, LEARNING, LEARNED, NEEDS_REVISION",
        )

    summary = _get_summary(db, subject.id)
    insight = next(
        (
            item
            for item in (summary.topic_insights or [])
            if (item.get("topic_key") or slugify_topic_key(item.get("topic_title", ""))) == topic_key
        ),
        None,
    )
    if insight is None:
        raise HTTPException(status_code=404, detail="Topic not found in analysed PYQs")

    topic_title = insight.get("topic_title") or payload.topic_title or topic_key
    row = db.scalar(
        select(StudentTopicLearning).where(
            StudentTopicLearning.student_profile_id == profile.id,
            StudentTopicLearning.subject_id == subject.id,
            StudentTopicLearning.topic_key == topic_key,
        )
    )
    if row is None:
        row = StudentTopicLearning(
            student_profile_id=profile.id,
            subject_id=subject.id,
            topic_key=topic_key,
            topic_title=topic_title,
            status=status,
            explanation=payload.explanation,
        )
        db.add(row)
    else:
        row.topic_title = topic_title
        row.status = status
        row.explanation = payload.explanation
        row.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)
    return {
        "message": "Topic progress updated",
        "topic_key": row.topic_key,
        "topic_title": row.topic_title,
        "status": row.status,
        "explanation": row.explanation,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/api/v1/student/questions")
def list_student_questions(
    subject_id: Optional[uuid.UUID] = None,
    topic_key: Optional[str] = None,
    bookmarked: Optional[bool] = None,
    repeated_only: bool = False,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = get_student_profile(db, student)
    subject_ids = enrolled_subject_ids(db, profile)
    if subject_id:
        _profile, subject = require_subject_access(db, student, subject_id)
        subject_ids = {subject.id}
    if not subject_ids:
        return {"items": [], "total": 0}

    statement = (
        select(Question, UploadedDocument, QuestionPaper, Subject)
        .join(UploadedDocument, Question.document_id == UploadedDocument.id)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .join(Subject, QuestionPaper.subject_id == Subject.id)
        .where(
            UploadedDocument.subject_id.in_(subject_ids),
            UploadedDocument.active.is_(True),
        )
    )
    if topic_key:
        topic_rows = db.execute(
            select(Question.id, QuestionClassification.main_topic)
            .join(QuestionClassification, QuestionClassification.question_id == Question.id)
            .join(UploadedDocument, Question.document_id == UploadedDocument.id)
            .where(UploadedDocument.subject_id.in_(subject_ids))
        ).all()
        matching_ids = [
            row[0]
            for row in topic_rows
            if slugify_topic_key(row[1] or "") == topic_key
        ]
        statement = statement.where(Question.id.in_(matching_ids or [uuid.UUID(int=0)]))
    if bookmarked is not None:
        bookmark_ids = select(PyqQuestionBookmark.question_id).where(
            PyqQuestionBookmark.student_profile_id == profile.id
        )
        statement = (
            statement.where(Question.id.in_(bookmark_ids))
            if bookmarked
            else statement.where(Question.id.notin_(bookmark_ids))
        )
    if repeated_only:
        repeated_ids = select(QuestionSimilarity.source_question_id).union(
            select(QuestionSimilarity.target_question_id)
        )
        statement = statement.where(Question.id.in_(repeated_ids))
    if search:
        statement = statement.where(Question.extracted_text.ilike(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(
        statement.order_by(UploadedDocument.uploaded_at.desc(), Question.sequence.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for question, document, paper, subject in rows:
        items.append(
            _question_payload(db, question, document, paper, subject, profile.id)
        )
    return {"items": items, "total": total}


@router.get("/api/v1/student/questions/{question_id}")
def get_student_question(
    question_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = get_student_profile(db, student)
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    document, paper, subject = _question_context(db, question)
    require_subject_access(db, student, subject.id)
    return _question_payload(db, question, document, paper, subject, profile.id)


@router.post("/api/v1/student/bookmarks/questions/{question_id}", status_code=201)
def bookmark_question(
    question_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = get_student_profile(db, student)
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    _document, _paper, subject = _question_context(db, question)
    require_subject_access(db, student, subject.id)

    existing = db.scalar(
        select(PyqQuestionBookmark).where(
            PyqQuestionBookmark.student_profile_id == profile.id,
            PyqQuestionBookmark.question_id == question.id,
        )
    )
    if existing is None:
        db.add(
            PyqQuestionBookmark(
                student_profile_id=profile.id,
                question_id=question.id,
            )
        )
        db.commit()
    return {"message": "Question bookmarked", "question_id": str(question.id), "bookmarked": True}


@router.delete("/api/v1/student/bookmarks/questions/{question_id}")
def remove_question_bookmark(
    question_id: uuid.UUID,
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = get_student_profile(db, student)
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    _document, _paper, subject = _question_context(db, question)
    require_subject_access(db, student, subject.id)

    existing = db.scalar(
        select(PyqQuestionBookmark).where(
            PyqQuestionBookmark.student_profile_id == profile.id,
            PyqQuestionBookmark.question_id == question.id,
        )
    )
    if existing is not None:
        db.delete(existing)
        db.commit()
    return {"message": "Bookmark removed", "question_id": str(question.id), "bookmarked": False}


@router.get("/api/v1/student/bookmarks/questions")
def list_bookmarked_questions(
    subject_id: Optional[uuid.UUID] = None,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    student: User = Depends(require_student),
    db: Session = Depends(get_db),
):
    profile = get_student_profile(db, student)
    subject_ids = enrolled_subject_ids(db, profile)
    if subject_id:
        _profile, subject = require_subject_access(db, student, subject_id)
        subject_ids = {subject.id}
    if not subject_ids:
        return {"items": [], "total": 0}

    statement = (
        select(Question, UploadedDocument, QuestionPaper, Subject, PyqQuestionBookmark)
        .join(PyqQuestionBookmark, PyqQuestionBookmark.question_id == Question.id)
        .join(UploadedDocument, Question.document_id == UploadedDocument.id)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .join(Subject, QuestionPaper.subject_id == Subject.id)
        .where(
            PyqQuestionBookmark.student_profile_id == profile.id,
            UploadedDocument.subject_id.in_(subject_ids),
            UploadedDocument.active.is_(True),
        )
        .order_by(desc(PyqQuestionBookmark.created_at))
    )
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.limit(limit).offset(offset)).all()
    items = []
    for question, document, paper, subject, bookmark in rows:
        payload = _question_payload(db, question, document, paper, subject, profile.id)
        payload["bookmarked_at"] = bookmark.created_at.isoformat() if bookmark.created_at else None
        items.append(payload)
    return {"items": items, "total": total}
