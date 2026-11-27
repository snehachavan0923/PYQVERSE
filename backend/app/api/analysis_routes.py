"""API endpoints for automated AI PYQ analysis engine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_student
from app.database.connection import get_db
from app.models.academic import Subject
from app.models.analysis import (
    AnalysisJob,
    AnalysisJobStatus,
    QuestionClassification,
    QuestionSimilarity,
    RepeatCategory,
    SubjectAnalysisSummary,
)
from app.models.document import QuestionPaper, UploadedDocument
from app.models.question import Question, QuestionTopicMap
from app.models.syllabus import Topic, Unit, VerificationStatus
from app.models.user import User
from app.services.pyq_analyzer import run_pyq_analysis_job
from app.services.pyq_statistics import compute_subject_analysis

router = APIRouter(tags=["analysis"])
logger = logging.getLogger(__name__)


class QuestionCorrectionRequest(BaseModel):
    extracted_text: Optional[str] = None
    marks: Optional[int] = None
    main_topic: Optional[str] = None
    subtopic: Optional[str] = None
    unit_number: Optional[int] = None
    topic_id: Optional[uuid.UUID] = None
    action: Optional[str] = "UPDATE"  # "APPROVE", "REJECT", "UPDATE"


@router.get("/api/v1/admin/analysis/jobs")
def get_analysis_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    subject_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all AI analysis jobs with execution status and metrics."""
    query = (
        select(AnalysisJob, QuestionPaper, UploadedDocument, Subject)
        .join(QuestionPaper, AnalysisJob.question_paper_id == QuestionPaper.id)
        .join(UploadedDocument, AnalysisJob.uploaded_document_id == UploadedDocument.id)
        .outerjoin(Subject, QuestionPaper.subject_id == Subject.id)
        .order_by(desc(AnalysisJob.created_at))
    )

    if status_filter:
        normalized = status_filter.strip().upper()
        if normalized in AnalysisJobStatus.__members__:
            query = query.where(AnalysisJob.status == AnalysisJobStatus(normalized))

    if subject_id:
        query = query.where(QuestionPaper.subject_id == subject_id)

    total_count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    results = db.execute(query.limit(limit).offset(offset)).all()

    items = []
    for job, paper, doc, subject in results:
        items.append({
            "id": str(job.id),
            "question_paper_id": str(job.question_paper_id),
            "uploaded_document_id": str(job.uploaded_document_id),
            "title": paper.title or doc.title or doc.original_filename,
            "original_filename": doc.original_filename,
            "subject_id": str(paper.subject_id),
            "subject_code": subject.code if subject else None,
            "subject_name": subject.name if subject else None,
            "exam_type": paper.exam_type.value,
            "examination_year": paper.examination_year,
            "status": job.status.value,
            "stage": job.stage,
            "progress_percent": job.progress_percent,
            "total_questions": job.total_questions,
            "mapped_questions": job.mapped_questions,
            "flagged_questions": job.flagged_questions,
            "average_confidence": job.average_confidence,
            "error_message": job.error_message,
            "model_name": job.model_name,
            "model_provider": job.model_provider,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })

    return {"items": items, "total": total_count}


@router.get("/api/v1/admin/analysis/jobs/{job_id}")
def get_analysis_job_detail(
    job_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Retrieve full detail for a single analysis job, including extracted questions."""
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    paper = db.get(QuestionPaper, job.question_paper_id)
    doc = db.get(UploadedDocument, job.uploaded_document_id)
    subject = db.get(Subject, paper.subject_id) if paper else None

    # Fetch extracted questions for document
    questions = (
        db.scalars(
            select(Question)
            .where(Question.document_id == job.uploaded_document_id)
            .order_by(Question.question_number.asc())
        )
        .all()
    )

    q_ids = [q.id for q in questions]
    classifications = {}
    if q_ids:
        cl_rows = db.scalars(
            select(QuestionClassification).where(QuestionClassification.question_id.in_(q_ids))
        ).all()
        for cl in cl_rows:
            classifications[cl.question_id] = cl

    question_items = []
    for q in questions:
        cl = classifications.get(q.id)
        question_items.append({
            "id": str(q.id),
            "question_number": q.question_number,
            "extracted_text": q.extracted_text,
            "marks": q.marks,
            "original_page_number": q.original_page_number,
            "verification_status": q.verification_status.value,
            "classification": {
                "main_topic": cl.main_topic if cl else None,
                "subtopic": cl.subtopic if cl else None,
                "related_concepts": cl.related_concepts if cl else [],
                "question_type": cl.question_type if cl else None,
                "difficulty": cl.difficulty if cl else None,
                "bloom_taxonomy": cl.bloom_taxonomy if cl else None,
                "unit_number": cl.unit_number if cl else None,
                "suggested_unit_title": cl.suggested_unit_title if cl else None,
                "suggested_topic_title": cl.suggested_topic_title if cl else None,
                "confidence": cl.confidence if cl else None,
                "explanation": cl.explanation if cl else None,
                "provisional": cl.provisional if cl else False,
            } if cl else None,
        })

    return {
        "id": str(job.id),
        "question_paper_id": str(job.question_paper_id),
        "uploaded_document_id": str(job.uploaded_document_id),
        "title": paper.title if paper else doc.original_filename,
        "subject_code": subject.code if subject else None,
        "subject_name": subject.name if subject else None,
        "status": job.status.value,
        "stage": job.stage,
        "progress_percent": job.progress_percent,
        "total_questions": job.total_questions,
        "mapped_questions": job.mapped_questions,
        "flagged_questions": job.flagged_questions,
        "average_confidence": job.average_confidence,
        "error_message": job.error_message,
        "questions": question_items,
    }


@router.post("/api/v1/admin/analysis/jobs/{job_id}/retry")
def retry_analysis_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger a retry of a failed or flagged analysis job."""
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found")

    job.status = AnalysisJobStatus.PENDING
    job.stage = "Queued for retry"
    job.progress_percent = 0
    job.error_message = None
    db.commit()

    background_tasks.add_task(run_pyq_analysis_job, job.id)
    return {"message": "Analysis job retry scheduled", "job_id": str(job.id), "status": job.status.value}


@router.get("/api/v1/admin/analysis/flagged")
def get_flagged_questions(
    subject_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Retrieve questions flagged for admin review."""
    query = (
        select(Question, QuestionClassification, UploadedDocument, QuestionPaper, Subject)
        .join(QuestionClassification, Question.id == QuestionClassification.question_id)
        .join(UploadedDocument, Question.document_id == UploadedDocument.id)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .outerjoin(Subject, QuestionPaper.subject_id == Subject.id)
        .where(
            (QuestionClassification.provisional.is_(True))
            | (QuestionClassification.confidence < 0.65)
            | (Question.verification_status.in_([VerificationStatus.DRAFT, VerificationStatus.PENDING]))
        )
        .order_by(desc(Question.created_at))
    )

    if subject_id:
        query = query.where(QuestionPaper.subject_id == subject_id)

    total_count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    results = db.execute(query.limit(limit).offset(offset)).all()

    items = []
    for q, cl, doc, paper, subject in results:
        items.append({
            "id": str(q.id),
            "question_number": q.question_number,
            "extracted_text": q.extracted_text,
            "marks": q.marks,
            "original_page_number": q.original_page_number,
            "verification_status": q.verification_status.value,
            "paper_id": str(paper.id),
            "paper_title": paper.title or doc.original_filename,
            "subject_id": str(subject.id) if subject else None,
            "subject_code": subject.code if subject else None,
            "subject_name": subject.name if subject else None,
            "storage_path": doc.storage_path,
            "classification": {
                "main_topic": cl.main_topic,
                "subtopic": cl.subtopic,
                "related_concepts": cl.related_concepts or [],
                "question_type": cl.question_type,
                "difficulty": cl.difficulty,
                "bloom_taxonomy": cl.bloom_taxonomy,
                "unit_number": cl.unit_number,
                "suggested_unit_title": cl.suggested_unit_title,
                "suggested_topic_title": cl.suggested_topic_title,
                "confidence": cl.confidence,
                "explanation": cl.explanation,
                "provisional": cl.provisional,
            },
        })

    return {"items": items, "total": total_count}


@router.patch("/api/v1/admin/analysis/questions/{question_id}")
def correct_question_analysis(
    question_id: uuid.UUID,
    payload: QuestionCorrectionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Correct, approve, or reject an extracted question classification."""
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    cl = db.scalar(
        select(QuestionClassification).where(QuestionClassification.question_id == question.id)
    )

    if payload.extracted_text is not None:
        question.extracted_text = payload.extracted_text.strip()
    if payload.marks is not None:
        question.marks = payload.marks

    if cl:
        if payload.main_topic is not None:
            cl.main_topic = payload.main_topic.strip()
        if payload.subtopic is not None:
            cl.subtopic = payload.subtopic.strip()
        if payload.unit_number is not None:
            cl.unit_number = payload.unit_number

    # Handle action
    action = (payload.action or "UPDATE").upper()
    doc = db.get(UploadedDocument, question.document_id)
    subject_id = doc.subject_id if doc else None

    if action == "APPROVE":
        question.verification_status = VerificationStatus.VERIFIED
        if cl:
            cl.provisional = False
            cl.confidence = 1.0
            cl.explanation = f"Manually verified and approved by admin {admin.full_name or admin.email}"

        # If topic_id supplied, link in QuestionTopicMap
        if payload.topic_id:
            topic = db.get(Topic, payload.topic_id)
            if topic:
                q_map = db.get(QuestionTopicMap, (question.id, topic.id))
                if not q_map:
                    q_map = QuestionTopicMap(
                        question_id=question.id,
                        topic_id=topic.id,
                        confidence=1.0,
                        verification_status=VerificationStatus.VERIFIED,
                    )
                    db.add(q_map)
                else:
                    q_map.confidence = 1.0
                    q_map.verification_status = VerificationStatus.VERIFIED

    elif action == "REJECT":
        question.verification_status = VerificationStatus.REJECTED
        if cl:
            cl.explanation = f"Rejected by admin {admin.full_name or admin.email}"

    db.commit()
    db.refresh(question)

    # Recalculate subject analysis if subject_id is known
    if subject_id:
        try:
            compute_subject_analysis(db, subject_id)
        except Exception as exc:
            logger.warning("Failed to refresh subject analysis after question correction: %s", exc)

    return {
        "message": f"Question {action.lower()}d successfully",
        "question_id": str(question.id),
        "verification_status": question.verification_status.value,
        "extracted_text": question.extracted_text,
        "marks": question.marks,
        "classification": {
            "main_topic": cl.main_topic if cl else None,
            "subtopic": cl.subtopic if cl else None,
            "unit_number": cl.unit_number if cl else None,
            "confidence": cl.confidence if cl else None,
            "provisional": cl.provisional if cl else False,
        } if cl else None,
    }


@router.get("/api/v1/student/analysis/{subject_id}")
def get_student_subject_analysis(
    subject_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve AI-powered PYQ analysis, topic priority rankings, and recommendations for students."""
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    summary = db.scalar(
        select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
    )

    if not summary:
        summary = compute_subject_analysis(db, subject_id)

    return {
        "subject_id": str(subject.id),
        "subject_code": subject.code,
        "subject_name": subject.name,
        "total_papers": summary.total_papers,
        "total_questions": summary.total_questions,
        "coverage_score": summary.coverage_score,
        "unit_stats": summary.unit_stats or [],
        "topic_insights": summary.topic_insights or [],
        "repeated_clusters": summary.repeated_question_clusters or [],
        "recommendations": summary.recommendations or {
            "study_first": [],
            "frequent_repeats": [],
            "revision_order": [],
            "coverage_gaps": [],
            "insufficient_data": True,
        },
        "calculated_at": summary.calculated_at.isoformat() if summary.calculated_at else None,
    }
