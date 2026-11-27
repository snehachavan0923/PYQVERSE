"""End-to-end background analysis job runner for PYQVERSE question papers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.analysis import AnalysisJob, AnalysisJobStatus, QuestionClassification
from app.models.document import QuestionPaper, UploadedDocument
from app.models.progress import PyqQuestionBookmark
from app.models.question import DocumentPage, Question, QuestionTopicMap
from app.models.syllabus import Subtopic, SyllabusVersion, Topic, Unit, VerificationStatus
from app.services import storage
from app.services.ai_provider import get_ai_provider
from app.services.pdf_extraction import extract_questions_from_pdf
from app.services.pyq_statistics import compute_subject_analysis, recompute_subject_similarities

logger = logging.getLogger(__name__)


def get_subject_syllabus_structure(db: Session, subject_id: UUID) -> List[Dict[str, Any]]:
    """Retrieve structured active syllabus units, topics, and subtopics for a subject."""
    active_version = db.scalar(
        select(SyllabusVersion)
        .where(SyllabusVersion.subject_id == subject_id, SyllabusVersion.active.is_(True))
        .order_by(SyllabusVersion.created_at.desc())
    )

    if not active_version:
        units = (
            db.scalars(
                select(Unit)
                .where(Unit.subject_id == subject_id, Unit.active.is_(True))
                .order_by(Unit.order_index.asc())
            )
            .all()
        )
    else:
        units = (
            db.scalars(
                select(Unit)
                .where(Unit.syllabus_version_id == active_version.id, Unit.active.is_(True))
                .order_by(Unit.order_index.asc())
            )
            .all()
        )

    structure: List[Dict[str, Any]] = []
    for unit in units:
        topics = (
            db.scalars(
                select(Topic).where(Topic.unit_id == unit.id).order_by(Topic.order_index.asc())
            )
            .all()
        )
        topics_data = []
        for topic in topics:
            subtopics = (
                db.scalars(
                    select(Subtopic).where(Subtopic.topic_id == topic.id).order_by(Subtopic.order_index.asc())
                )
                .all()
            )
            topics_data.append(
                {
                    "id": topic.id,
                    "title": topic.title,
                    "order_index": topic.order_index,
                    "subtopics": [{"id": sub.id, "title": sub.title} for sub in subtopics],
                }
            )
        structure.append(
            {
                "id": unit.id,
                "title": unit.title,
                "order_index": unit.order_index,
                "topics": topics_data,
            }
        )

    return structure


def _question_is_bookmarked(db: Session, question_id: UUID) -> bool:
    return (
        db.scalar(
            select(PyqQuestionBookmark.id).where(PyqQuestionBookmark.question_id == question_id)
        )
        is not None
    )


def run_pyq_analysis_job(job_id: UUID, db_session: Optional[Session] = None) -> Optional[AnalysisJob]:
    """Execute the automated PYQ analysis pipeline for a specific AnalysisJob."""
    owns_session = db_session is None
    db = db_session if db_session is not None else SessionLocal()

    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            logger.warning("AnalysisJob %s not found", job_id)
            return None

        paper = db.get(QuestionPaper, job.question_paper_id)
        document = db.get(UploadedDocument, job.uploaded_document_id)
        if not paper or not document:
            job.status = AnalysisJobStatus.FAILED
            job.error_message = "Associated QuestionPaper or UploadedDocument missing"
            db.commit()
            return job

        job.started_at = datetime.now(timezone.utc)
        job.error_message = None

        # ---------------- STAGE 1: EXTRACTING ----------------
        job.status = AnalysisJobStatus.EXTRACTING
        job.stage = "Extracting text and question hierarchy from PDF"
        job.progress_percent = 15
        db.commit()

        try:
            pdf_bytes = storage.download_bytes(document.storage_path)
        except Exception as exc:
            logger.exception("Failed to download PDF bytes for document %s: %s", document.id, exc)
            job.status = AnalysisJobStatus.FAILED
            job.error_message = f"Failed to download PDF from storage: {exc}"
            db.commit()
            return job

        extraction_result = extract_questions_from_pdf(pdf_bytes)

        existing_pages = db.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        ).all()
        existing_page_numbers = {page.page_number for page in existing_pages}
        for page in extraction_result.pages:
            if page.page_number not in existing_page_numbers:
                db.add(
                    DocumentPage(
                        document_id=document.id,
                        page_number=page.page_number,
                        extracted_text=page.text,
                    )
                )

        # Questions are identified by their stable extraction sequence.  This
        # allows printed question numbers to repeat across pages/combined papers
        # without colliding, while preserving bookmarks on re-analysis.
        existing_questions = db.scalars(
            select(Question).where(Question.document_id == document.id)
        ).all()
        question_by_sequence = {question.sequence: question for question in existing_questions}
        extracted_sequences = set()

        saved_questions: List[Question] = []
        for extracted in extraction_result.questions:
            extracted_sequences.add(extracted.sequence)
            question_row = question_by_sequence.get(extracted.sequence)
            if question_row:
                question_row.question_number = extracted.question_number
                question_row.extracted_text = extracted.extracted_text
                question_row.marks = extracted.marks
                question_row.original_page_number = extracted.original_page_number
            else:
                question_row = Question(
                    document_id=document.id,
                    question_number=extracted.question_number,
                    sequence=extracted.sequence,
                    extracted_text=extracted.extracted_text,
                    marks=extracted.marks,
                    original_page_number=extracted.original_page_number,
                    verification_status=VerificationStatus.DRAFT,
                )
                db.add(question_row)
            saved_questions.append(question_row)

        # Remove stale rows from an earlier extraction, but never delete a row a
        # student has bookmarked.
        for sequence, question_row in question_by_sequence.items():
            if sequence in extracted_sequences:
                continue
            if _question_is_bookmarked(db, question_row.id):
                continue
            db.delete(question_row)

        db.flush()
        job.total_questions = len(saved_questions)
        job.progress_percent = 35
        db.commit()

        if not saved_questions:
            job.status = AnalysisJobStatus.FAILED
            job.stage = "Extraction finished without readable questions"
            job.error_message = (
                "; ".join(extraction_result.notes)
                or "No questions could be extracted from this PDF. The document may be scanned or image-only."
            )
            job.completed_at = datetime.now(timezone.utc)
            job.model_name = "pyqverse-extraction-v2"
            job.model_provider = "deterministic"
            db.commit()
            db.refresh(job)
            return job

        # ---------------- STAGE 2: CLASSIFYING & MAPPING ----------------
        job.status = AnalysisJobStatus.CLASSIFYING
        job.stage = "Classifying questions and discovering provisional topics"
        job.progress_percent = 45
        db.commit()

        ai_provider = get_ai_provider()
        syllabus_structure = get_subject_syllabus_structure(db, paper.subject_id)
        subject_code = None
        subject_name = None
        if paper.subject_id:
            from app.models.academic import Subject

            subject = db.get(Subject, paper.subject_id)
            if subject:
                subject_code = subject.code
                subject_name = subject.name

        topic_lookup_by_title: Dict[str, Topic] = {}
        for unit in syllabus_structure:
            for topic_data in unit.get("topics", []):
                topic_obj = db.get(Topic, topic_data["id"])
                if topic_obj:
                    topic_lookup_by_title[topic_obj.title.lower()] = topic_obj

        mapped_count = 0
        flagged_count = 0
        confidence_sum = 0.0

        for question in saved_questions:
            classification_result = ai_provider.classify_question(
                question_text=question.extracted_text,
                marks=question.marks,
                syllabus_units=syllabus_structure,
                subject_code=subject_code,
                subject_name=subject_name,
            )
            confidence_sum += classification_result.confidence

            existing_classification = db.scalar(
                select(QuestionClassification).where(
                    QuestionClassification.question_id == question.id
                )
            )
            if existing_classification:
                classification = existing_classification
            else:
                classification = QuestionClassification(question_id=question.id)
                db.add(classification)

            classification.main_topic = classification_result.main_topic
            classification.subtopic = classification_result.subtopic
            classification.related_concepts = classification_result.related_concepts
            classification.question_type = classification_result.question_type
            classification.difficulty = classification_result.difficulty
            classification.bloom_taxonomy = classification_result.bloom_taxonomy
            classification.unit_number = classification_result.unit_number
            classification.suggested_unit_title = classification_result.suggested_unit_title
            classification.suggested_topic_title = classification_result.suggested_topic_title
            classification.confidence = classification_result.confidence
            classification.explanation = classification_result.explanation
            classification.provisional = classification_result.provisional
            classification.model_name = classification_result.model_name
            classification.model_provider = classification_result.model_provider

            target_topic = None
            if classification_result.suggested_topic_title:
                target_topic = topic_lookup_by_title.get(
                    classification_result.suggested_topic_title.lower()
                )
            if target_topic:
                question_topic_map = db.get(QuestionTopicMap, (question.id, target_topic.id))
                map_status = (
                    VerificationStatus.VERIFIED
                    if classification_result.confidence >= 0.80
                    else VerificationStatus.PENDING
                )
                if not question_topic_map:
                    question_topic_map = QuestionTopicMap(
                        question_id=question.id,
                        topic_id=target_topic.id,
                        confidence=classification_result.confidence,
                        verification_status=map_status,
                    )
                    db.add(question_topic_map)
                else:
                    question_topic_map.confidence = classification_result.confidence
                    question_topic_map.verification_status = map_status
                mapped_count += 1

            if classification_result.confidence >= 0.80:
                question.verification_status = VerificationStatus.VERIFIED
            elif classification_result.confidence >= 0.65:
                question.verification_status = VerificationStatus.PENDING
            else:
                question.verification_status = VerificationStatus.DRAFT
                flagged_count += 1

        db.flush()
        job.mapped_questions = mapped_count
        job.flagged_questions = flagged_count
        job.average_confidence = round(confidence_sum / max(len(saved_questions), 1), 2)
        job.progress_percent = 65
        db.commit()

        # ---------------- STAGE 3: REPETITION DETECTION ----------------
        job.status = AnalysisJobStatus.MAPPING
        job.stage = "Detecting exact and reworded repeats across the subject"
        job.progress_percent = 75
        db.commit()

        recompute_subject_similarities(db, paper.subject_id)

        # ---------------- STAGE 4: STATISTICAL ANALYSIS ----------------
        job.status = AnalysisJobStatus.ANALYZING
        job.stage = "Aggregating topic frequencies, marks, and historical priority"
        job.progress_percent = 90
        db.commit()

        compute_subject_analysis(db, paper.subject_id)

        # ---------------- STAGE 5: COMPLETION ----------------
        if flagged_count > 0:
            job.status = AnalysisJobStatus.FLAGGED_REVIEW
            job.stage = f"Completed with {flagged_count} provisional question(s) flagged for review"
        else:
            job.status = AnalysisJobStatus.COMPLETED
            job.stage = "Analysis complete"

        if extraction_result.low_confidence_extraction:
            note = "; ".join(extraction_result.notes)
            if note:
                job.stage = f"{job.stage}. {note}"

        job.progress_percent = 100
        job.completed_at = datetime.now(timezone.utc)
        job.model_name = ai_provider.model_name
        job.model_provider = ai_provider.model_provider
        db.commit()
        db.refresh(job)
        return job

    except Exception as exc:
        logger.exception("Error during analysis job %s: %s", job_id, exc)
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        if job:
            job.status = AnalysisJobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        if owns_session:
            db.close()
