"""API endpoints for the automated PYQ analysis engine and student insights."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
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
from app.models.progress import PyqQuestionBookmark, StudentTopicLearning
from app.models.question import Question, QuestionTopicMap
from app.models.syllabus import Topic, Unit, VerificationStatus
from app.models.user import User
from app.services.ai_provider import get_ai_provider_status
from app.services.pyq_analyzer import run_pyq_analysis_job
from app.services.pyq_statistics import compute_subject_analysis
from app.services.student_access import require_subject_access

router = APIRouter(tags=["analysis"])
logger = logging.getLogger(__name__)

PROCESSING_STATUSES = {
    AnalysisJobStatus.PENDING,
    AnalysisJobStatus.EXTRACTING,
    AnalysisJobStatus.CLASSIFYING,
    AnalysisJobStatus.MAPPING,
    AnalysisJobStatus.ANALYZING,
}


class QuestionCorrectionRequest(BaseModel):
    extracted_text: Optional[str] = None
    marks: Optional[int] = None
    main_topic: Optional[str] = None
    subtopic: Optional[str] = None
    unit_number: Optional[int] = None
    topic_id: Optional[uuid.UUID] = None
    action: Optional[str] = "UPDATE"  # "APPROVE", "REJECT", "UPDATE"


class AnalysisSyncRequest(BaseModel):
    run: bool = True
    force: bool = False


def _job_payload(job: AnalysisJob, paper: QuestionPaper, document: UploadedDocument, subject: Optional[Subject]) -> Dict[str, Any]:
    return {
        "id": str(job.id),
        "question_paper_id": str(job.question_paper_id),
        "uploaded_document_id": str(job.uploaded_document_id),
        "title": paper.title or document.title or document.original_filename,
        "original_filename": document.original_filename,
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
    }


def _paper_question_counts(db: Session, document_id: uuid.UUID) -> tuple[int, int, int]:
    total = db.scalar(
        select(func.count()).select_from(Question).where(Question.document_id == document_id)
    ) or 0
    classified = db.scalar(
        select(func.count())
        .select_from(QuestionClassification)
        .join(Question, Question.id == QuestionClassification.question_id)
        .where(Question.document_id == document_id)
    ) or 0
    flagged = db.scalar(
        select(func.count())
        .select_from(Question)
        .where(
            Question.document_id == document_id,
            Question.verification_status == VerificationStatus.DRAFT,
        )
    ) or 0
    return int(total), int(classified), int(flagged)


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
    items = [_job_payload(job, paper, doc, subject) for job, paper, doc, subject in results]
    return {"items": items, "total": total_count}


@router.get("/api/v1/admin/analysis/overview")
def get_analysis_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Document-level overview including papers that never received a job."""
    rows = db.execute(
        select(UploadedDocument, QuestionPaper, Subject)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .outerjoin(Subject, QuestionPaper.subject_id == Subject.id)
        .where(UploadedDocument.active.is_(True))
        .order_by(UploadedDocument.uploaded_at)
    ).all()

    papers: List[Dict[str, Any]] = []
    counts = {
        "total_documents": len(rows),
        "pending_jobs": 0,
        "processing_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "flagged_jobs": 0,
        "documents_without_jobs": 0,
        "extracted_questions": 0,
        "classified_questions": 0,
        "flagged_questions": 0,
    }

    for document, paper, subject in rows:
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.question_paper_id == paper.id)
            .order_by(desc(AnalysisJob.created_at))
        )
        total, classified, flagged = _paper_question_counts(db, document.id)
        counts["extracted_questions"] += total
        counts["classified_questions"] += classified
        counts["flagged_questions"] += flagged

        if job is None:
            counts["documents_without_jobs"] += 1
        elif job.status == AnalysisJobStatus.PENDING:
            counts["pending_jobs"] += 1
        elif job.status in PROCESSING_STATUSES:
            counts["processing_jobs"] += 1
        elif job.status == AnalysisJobStatus.COMPLETED:
            counts["completed_jobs"] += 1
        elif job.status == AnalysisJobStatus.FAILED:
            counts["failed_jobs"] += 1
        elif job.status == AnalysisJobStatus.FLAGGED_REVIEW:
            counts["flagged_jobs"] += 1

        papers.append(
            {
                "paper_id": str(paper.id),
                "document_id": str(document.id),
                "title": paper.title or document.title or document.original_filename,
                "original_filename": document.original_filename,
                "subject_id": str(paper.subject_id),
                "subject_code": subject.code if subject else None,
                "subject_name": subject.name if subject else None,
                "exam_type": paper.exam_type.value,
                "examination_year": paper.examination_year,
                "cie_number": paper.cie_number,
                "job_id": str(job.id) if job else None,
                "job_status": job.status.value if job else "NOT_QUEUED",
                "stage": job.stage if job else "No analysis job has been created for this paper",
                "progress_percent": job.progress_percent if job else 0,
                "error_message": job.error_message if job else None,
                "question_count": total,
                "classified_count": classified,
                "flagged_count": flagged,
                "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
            }
        )

    return {
        **counts,
        "papers": papers,
        "ai_provider": get_ai_provider_status(),
    }


@router.post("/api/v1/admin/analysis/sync")
def sync_analysis_jobs(
    payload: AnalysisSyncRequest,
    background_tasks: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create jobs for papers that have never been analysed (or retry failures)."""
    rows = db.execute(
        select(UploadedDocument, QuestionPaper)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .where(UploadedDocument.active.is_(True))
        .order_by(UploadedDocument.uploaded_at)
    ).all()

    scheduled: List[str] = []
    created = 0
    reset = 0
    skipped = 0

    for document, paper in rows:
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.question_paper_id == paper.id)
            .order_by(desc(AnalysisJob.created_at))
        )
        should_run = False
        if job is None:
            job = AnalysisJob(
                question_paper_id=paper.id,
                uploaded_document_id=document.id,
                status=AnalysisJobStatus.PENDING,
                stage="Queued for automated analysis",
                progress_percent=0,
            )
            db.add(job)
            db.flush()
            created += 1
            should_run = True
        elif payload.force or job.status == AnalysisJobStatus.FAILED:
            job.status = AnalysisJobStatus.PENDING
            job.stage = "Queued for automated analysis"
            job.progress_percent = 0
            job.error_message = None
            reset += 1
            should_run = True
        elif job.status in PROCESSING_STATUSES:
            should_run = False
            skipped += 1
        else:
            skipped += 1

        if should_run:
            scheduled.append(str(job.id))
            if payload.run:
                background_tasks.add_task(run_pyq_analysis_job, job.id)

    db.commit()
    return {
        "message": "Analysis jobs synchronised",
        "created": created,
        "reset": reset,
        "skipped": skipped,
        "scheduled_job_ids": scheduled,
        "run": payload.run,
    }


@router.post("/api/v1/admin/analysis/papers/{paper_id}/analyze")
def analyze_single_paper(
    paper_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    force: bool = True,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    paper = db.get(QuestionPaper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Question paper not found")
    document = db.get(UploadedDocument, paper.uploaded_document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Uploaded document not found")

    job = db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.question_paper_id == paper.id)
        .order_by(desc(AnalysisJob.created_at))
    )
    if job is None or force:
        if job is None:
            job = AnalysisJob(
                question_paper_id=paper.id,
                uploaded_document_id=document.id,
            )
            db.add(job)
        job.status = AnalysisJobStatus.PENDING
        job.stage = "Queued for automated analysis"
        job.progress_percent = 0
        job.error_message = None
        db.commit()
        db.refresh(job)

    background_tasks.add_task(run_pyq_analysis_job, job.id)
    return {"message": "Analysis scheduled", "job_id": str(job.id), "status": job.status.value}


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
    document = db.get(UploadedDocument, job.uploaded_document_id)
    subject = db.get(Subject, paper.subject_id) if paper else None

    questions = (
        db.scalars(
            select(Question)
            .where(Question.document_id == job.uploaded_document_id)
            .order_by(Question.sequence.asc())
        )
        .all()
    )
    question_ids = [question.id for question in questions]
    classifications = {}
    if question_ids:
        classifications = {
            classification.question_id: classification
            for classification in db.scalars(
                select(QuestionClassification).where(
                    QuestionClassification.question_id.in_(question_ids)
                )
            ).all()
        }

    question_items = []
    for question in questions:
        classification = classifications.get(question.id)
        question_items.append(
            {
                "id": str(question.id),
                "question_number": question.question_number,
                "sequence": question.sequence,
                "extracted_text": question.extracted_text,
                "marks": question.marks,
                "original_page_number": question.original_page_number,
                "verification_status": question.verification_status.value,
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
            }
        )

    return {
        "id": str(job.id),
        "question_paper_id": str(job.question_paper_id),
        "uploaded_document_id": str(job.uploaded_document_id),
        "title": paper.title if paper else document.original_filename,
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
            (QuestionClassification.confidence < 0.65)
            | (Question.verification_status == VerificationStatus.DRAFT)
        )
        .order_by(desc(Question.created_at))
    )
    if subject_id:
        query = query.where(QuestionPaper.subject_id == subject_id)

    total_count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    results = db.execute(query.limit(limit).offset(offset)).all()

    items = []
    for question, classification, document, paper, subject in results:
        items.append(
            {
                "id": str(question.id),
                "question_number": question.question_number,
                "extracted_text": question.extracted_text,
                "marks": question.marks,
                "original_page_number": question.original_page_number,
                "verification_status": question.verification_status.value,
                "paper_id": str(paper.id),
                "paper_title": paper.title or document.original_filename,
                "subject_id": str(subject.id) if subject else None,
                "subject_code": subject.code if subject else None,
                "subject_name": subject.name if subject else None,
                "storage_path": document.storage_path,
                "classification": {
                    "main_topic": classification.main_topic,
                    "subtopic": classification.subtopic,
                    "related_concepts": classification.related_concepts or [],
                    "question_type": classification.question_type,
                    "difficulty": classification.difficulty,
                    "bloom_taxonomy": classification.bloom_taxonomy,
                    "unit_number": classification.unit_number,
                    "suggested_unit_title": classification.suggested_unit_title,
                    "suggested_topic_title": classification.suggested_topic_title,
                    "confidence": classification.confidence,
                    "explanation": classification.explanation,
                    "provisional": classification.provisional,
                },
            }
        )

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

    classification = db.scalar(
        select(QuestionClassification).where(QuestionClassification.question_id == question.id)
    )

    if payload.extracted_text is not None:
        question.extracted_text = payload.extracted_text.strip()
    if payload.marks is not None:
        question.marks = payload.marks

    if classification:
        if payload.main_topic is not None:
            classification.main_topic = payload.main_topic.strip()
        if payload.subtopic is not None:
            classification.subtopic = payload.subtopic.strip()
        if payload.unit_number is not None:
            classification.unit_number = payload.unit_number

    action = (payload.action or "UPDATE").upper()
    document = db.get(UploadedDocument, question.document_id)
    subject_id = document.subject_id if document else None

    if action == "APPROVE":
        question.verification_status = VerificationStatus.VERIFIED
        if classification:
            classification.provisional = False
            classification.confidence = 1.0
            classification.explanation = (
                f"Manually verified and approved by admin {admin.full_name or admin.email}"
            )
        if payload.topic_id:
            topic = db.get(Topic, payload.topic_id)
            if topic:
                question_topic_map = db.get(QuestionTopicMap, (question.id, topic.id))
                if not question_topic_map:
                    question_topic_map = QuestionTopicMap(
                        question_id=question.id,
                        topic_id=topic.id,
                        confidence=1.0,
                        verification_status=VerificationStatus.VERIFIED,
                    )
                    db.add(question_topic_map)
                else:
                    question_topic_map.confidence = 1.0
                    question_topic_map.verification_status = VerificationStatus.VERIFIED
    elif action == "REJECT":
        question.verification_status = VerificationStatus.REJECTED
        if classification:
            classification.explanation = (
                f"Rejected by admin {admin.full_name or admin.email}"
            )

    db.commit()
    db.refresh(question)

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
            "main_topic": classification.main_topic if classification else None,
            "subtopic": classification.subtopic if classification else None,
            "unit_number": classification.unit_number if classification else None,
            "confidence": classification.confidence if classification else None,
            "provisional": classification.provisional if classification else False,
        }
        if classification
        else None,
    }


def _subject_paper_status(db: Session, subject_id: uuid.UUID) -> List[Dict[str, Any]]:
    rows = db.execute(
        select(UploadedDocument, QuestionPaper)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .where(
            QuestionPaper.subject_id == subject_id,
            UploadedDocument.active.is_(True),
        )
        .order_by(UploadedDocument.uploaded_at)
    ).all()
    papers = []
    for row in rows:
        try:
            document, paper = row
        except (TypeError, ValueError):
            continue
        job = db.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.question_paper_id == paper.id)
            .order_by(desc(AnalysisJob.created_at))
        )
        total, classified, flagged = _paper_question_counts(db, document.id)
        papers.append(
            {
                "paper_id": str(paper.id),
                "document_id": str(document.id),
                "original_filename": document.original_filename,
                "title": paper.title or document.original_filename,
                "exam_type": paper.exam_type.value,
                "examination_year": paper.examination_year,
                "cie_number": paper.cie_number,
                "job_status": job.status.value if job else "NOT_QUEUED",
                "stage": job.stage if job else "No analysis job has been created",
                "progress_percent": job.progress_percent if job else 0,
                "question_count": total,
                "classified_count": classified,
                "flagged_count": flagged,
                "error_message": job.error_message if job else None,
            }
        )
    return papers


@router.get("/api/v1/student/analysis/{subject_id}")
def get_student_subject_analysis(
    subject_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve actual PYQ analysis, provisional topics, repeats and progress."""
    profile, subject = require_subject_access(db, user, subject_id)

    summary = db.scalar(
        select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
    )
    if not summary:
        summary = compute_subject_analysis(db, subject_id)

    papers = _subject_paper_status(db, subject_id)
    topic_insights = summary.topic_insights or []
    repeated_clusters = summary.repeated_question_clusters or []
    recommendations = summary.recommendations or {}

    bookmarked_ids: List[str] = []
    question_ids = [
        row[0]
        for row in db.execute(
            select(Question.id)
            .join(UploadedDocument, Question.document_id == UploadedDocument.id)
            .where(UploadedDocument.subject_id == subject_id)
        ).all()
        if isinstance(row[0], uuid.UUID)
    ]
    if question_ids:
        bookmarked_ids = [
            str(row)
            for row in db.scalars(
                select(PyqQuestionBookmark.question_id).where(
                    PyqQuestionBookmark.student_profile_id == profile.id,
                    PyqQuestionBookmark.question_id.in_(question_ids),
                )
            ).all()
        ]

    progress_rows = db.scalars(
        select(StudentTopicLearning).where(
            StudentTopicLearning.student_profile_id == profile.id,
            StudentTopicLearning.subject_id == subject_id,
        )
    ).all()
    topic_progress = [
        {
            "topic_key": row.topic_key,
            "topic_title": row.topic_title,
            "status": row.status,
            "explanation": row.explanation,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in progress_rows
    ]

    syllabus_status = recommendations.get("syllabus_status", "PENDING")
    data_availability = "AVAILABLE"
    if summary.total_questions == 0:
        data_availability = "NO_QUESTIONS"
    elif any(paper["job_status"] in {"FAILED", "NOT_QUEUED"} for paper in papers):
        data_availability = "PARTIAL"

    return {
        "subject_id": str(subject.id),
        "subject_code": subject.code,
        "subject_name": subject.name,
        "total_papers": summary.total_papers,
        "total_questions": summary.total_questions,
        "coverage_score": None if syllabus_status == "PENDING" else summary.coverage_score,
        "syllabus_status": syllabus_status,
        "data_availability": data_availability,
        "topics_discovered": len(topic_insights),
        "repeated_question_count": len(repeated_clusters),
        "unit_stats": summary.unit_stats or [],
        "topic_insights": topic_insights,
        "repeated_clusters": repeated_clusters,
        "recommendations": recommendations,
        "papers": papers,
        "ai_provider": recommendations.get("ai_provider") or get_ai_provider_status(),
        "bookmarked_question_ids": bookmarked_ids,
        "topic_progress": topic_progress,
        "calculated_at": summary.calculated_at.isoformat() if summary.calculated_at else None,
    }
