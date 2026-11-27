"""End-to-end background analysis job runner for PYQVERSE question papers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.analysis import (
    AnalysisJob,
    AnalysisJobStatus,
    QuestionClassification,
    QuestionSimilarity,
    RepeatCategory,
)
from app.models.document import QuestionPaper, UploadedDocument
from app.models.question import DocumentPage, Question, QuestionOccurrence, QuestionTopicMap
from app.models.syllabus import Subtopic, SyllabusDocument, SyllabusVersion, Topic, Unit, VerificationStatus
from app.services import storage
from app.services.ai_provider import get_ai_provider
from app.services.pdf_extraction import extract_questions_from_pdf
from app.services.pyq_statistics import compute_subject_analysis

logger = logging.getLogger(__name__)


def get_subject_syllabus_structure(db: Session, subject_id: UUID) -> List[Dict[str, Any]]:
    """Retrieve structured active syllabus units, topics, and subtopics for a subject."""
    active_version = db.scalar(
        select(SyllabusVersion)
        .where(SyllabusVersion.subject_id == subject_id, SyllabusVersion.active.is_(True))
        .order_by(SyllabusVersion.created_at.desc())
    )

    if not active_version:
        # Fallback to any units belonging to the subject
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
    for u in units:
        topics = (
            db.scalars(
                select(Topic).where(Topic.unit_id == u.id).order_by(Topic.order_index.asc())
            )
            .all()
        )
        topics_data = []
        for t in topics:
            subtopics = (
                db.scalars(
                    select(Subtopic).where(Subtopic.topic_id == t.id).order_by(Subtopic.order_index.asc())
                )
                .all()
            )
            topics_data.append({
                "id": t.id,
                "title": t.title,
                "order_index": t.order_index,
                "subtopics": [{"id": st.id, "title": st.title} for st in subtopics],
            })
        structure.append({
            "id": u.id,
            "title": u.title,
            "order_index": u.order_index,
            "topics": topics_data,
        })

    return structure


def run_pyq_analysis_job(job_id: UUID, db_session: Optional[Session] = None) -> AnalysisJob:
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

        # Store DocumentPage entries
        existing_pages = db.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        ).all()
        existing_page_nums = {p.page_number for p in existing_pages}

        for page in extraction_result.pages:
            if page.page_number not in existing_page_nums:
                doc_page = DocumentPage(
                    document_id=document.id,
                    page_number=page.page_number,
                    extracted_text=page.text,
                )
                db.add(doc_page)

        # Store or reconcile Questions
        existing_questions = db.scalars(
            select(Question).where(Question.document_id == document.id)
        ).all()
        q_map = {q.question_number: q for q in existing_questions}

        saved_questions: List[Question] = []
        for eq in extraction_result.questions:
            if eq.question_number in q_map:
                q_row = q_map[eq.question_number]
                q_row.extracted_text = eq.extracted_text
                q_row.marks = eq.marks
                q_row.original_page_number = eq.original_page_number
            else:
                q_row = Question(
                    document_id=document.id,
                    question_number=eq.question_number,
                    extracted_text=eq.extracted_text,
                    marks=eq.marks,
                    original_page_number=eq.original_page_number,
                    verification_status=VerificationStatus.DRAFT,
                )
                db.add(q_row)
            saved_questions.append(q_row)

        db.flush()
        job.total_questions = len(saved_questions)
        job.progress_percent = 35
        db.commit()

        # ---------------- STAGE 2: CLASSIFYING & MAPPING ----------------
        job.status = AnalysisJobStatus.CLASSIFYING
        job.stage = "Classifying questions and mapping to syllabus topics"
        job.progress_percent = 45
        db.commit()

        ai_provider = get_ai_provider()
        syllabus_structure = get_subject_syllabus_structure(db, paper.subject_id)

        # Build topic lookup by title and ID
        topic_lookup_by_title: Dict[str, Topic] = {}
        for u in syllabus_structure:
            for t_data in u.get("topics", []):
                t_obj = db.get(Topic, t_data["id"])
                if t_obj:
                    topic_lookup_by_title[t_obj.title.lower()] = t_obj

        mapped_count = 0
        flagged_count = 0
        conf_sum = 0.0

        for q in saved_questions:
            classification_result = ai_provider.classify_question(
                question_text=q.extracted_text,
                marks=q.marks,
                syllabus_units=syllabus_structure,
            )

            conf_sum += classification_result.confidence

            # Upsert QuestionClassification
            existing_cl = db.scalar(
                select(QuestionClassification).where(QuestionClassification.question_id == q.id)
            )
            if existing_cl:
                existing_cl.main_topic = classification_result.main_topic
                existing_cl.subtopic = classification_result.subtopic
                existing_cl.related_concepts = classification_result.related_concepts
                existing_cl.question_type = classification_result.question_type
                existing_cl.difficulty = classification_result.difficulty
                existing_cl.bloom_taxonomy = classification_result.bloom_taxonomy
                existing_cl.unit_number = classification_result.unit_number
                existing_cl.suggested_unit_title = classification_result.suggested_unit_title
                existing_cl.suggested_topic_title = classification_result.suggested_topic_title
                existing_cl.confidence = classification_result.confidence
                existing_cl.explanation = classification_result.explanation
                existing_cl.provisional = classification_result.provisional
                existing_cl.model_name = classification_result.model_name
                existing_cl.model_provider = classification_result.model_provider
            else:
                new_cl = QuestionClassification(
                    question_id=q.id,
                    main_topic=classification_result.main_topic,
                    subtopic=classification_result.subtopic,
                    related_concepts=classification_result.related_concepts,
                    question_type=classification_result.question_type,
                    difficulty=classification_result.difficulty,
                    bloom_taxonomy=classification_result.bloom_taxonomy,
                    unit_number=classification_result.unit_number,
                    suggested_unit_title=classification_result.suggested_unit_title,
                    suggested_topic_title=classification_result.suggested_topic_title,
                    confidence=classification_result.confidence,
                    explanation=classification_result.explanation,
                    provisional=classification_result.provisional,
                    model_name=classification_result.model_name,
                    model_provider=classification_result.model_provider,
                )
                db.add(new_cl)

            # Map to QuestionTopicMap if candidate topic exists
            target_topic = None
            if classification_result.suggested_topic_title:
                target_topic = topic_lookup_by_title.get(classification_result.suggested_topic_title.lower())

            if target_topic:
                q_topic_map = db.get(QuestionTopicMap, (q.id, target_topic.id))
                map_status = (
                    VerificationStatus.VERIFIED
                    if classification_result.confidence >= 0.80
                    else VerificationStatus.PENDING
                )
                if not q_topic_map:
                    q_topic_map = QuestionTopicMap(
                        question_id=q.id,
                        topic_id=target_topic.id,
                        confidence=classification_result.confidence,
                        verification_status=map_status,
                    )
                    db.add(q_topic_map)
                else:
                    q_topic_map.confidence = classification_result.confidence
                    q_topic_map.verification_status = map_status
                mapped_count += 1

            # Confidence decision logic
            if classification_result.confidence >= 0.80:
                q.verification_status = VerificationStatus.VERIFIED
            elif classification_result.confidence >= 0.60:
                q.verification_status = VerificationStatus.PENDING
            else:
                q.verification_status = VerificationStatus.DRAFT
                flagged_count += 1

        db.flush()
        job.mapped_questions = mapped_count
        job.flagged_questions = flagged_count
        job.average_confidence = round(conf_sum / max(len(saved_questions), 1), 2)
        job.progress_percent = 65
        db.commit()

        # ---------------- STAGE 3: REPETITION DETECTION ----------------
        job.status = AnalysisJobStatus.MAPPING
        job.stage = "Detecting exact and semantically similar repeats"
        job.progress_percent = 75
        db.commit()

        # Retrieve prior questions for this subject across other documents
        other_questions = (
            db.scalars(
                select(Question)
                .join(UploadedDocument, Question.document_id == UploadedDocument.id)
                .where(
                    UploadedDocument.subject_id == paper.subject_id,
                    Question.document_id != document.id,
                )
            )
            .all()
        )

        for q in saved_questions:
            for oq in other_questions:
                # Compare question pairs
                sim_res = ai_provider.compare_questions(q.extracted_text, oq.extracted_text)
                if sim_res.similarity_score >= 0.40:
                    # Upsert similarity pair
                    existing_sim = db.scalar(
                        select(QuestionSimilarity).where(
                            QuestionSimilarity.source_question_id == q.id,
                            QuestionSimilarity.target_question_id == oq.id,
                        )
                    )
                    if not existing_sim:
                        existing_sim = QuestionSimilarity(
                            source_question_id=q.id,
                            target_question_id=oq.id,
                            similarity_score=sim_res.similarity_score,
                            repeat_category=sim_res.repeat_category,
                            explanation=sim_res.explanation,
                        )
                        db.add(existing_sim)

                    # If exact repeat or reworded repeat, record QuestionOccurrence
                    if sim_res.repeat_category in [RepeatCategory.EXACT_REPEAT, RepeatCategory.REWORDED_REPEAT]:
                        db.add(
                            QuestionOccurrence(
                                question_id=oq.id,
                                document_id=document.id,
                                occurrence_label=f"Repeated in {paper.examination_year} ({q.question_number})",
                            )
                        )

        db.flush()
        job.progress_percent = 85
        db.commit()

        # ---------------- STAGE 4: STATISTICAL ANALYSIS & INSIGHTS ----------------
        job.status = AnalysisJobStatus.ANALYZING
        job.stage = "Aggregating topic frequencies, priority scores, and student recommendations"
        job.progress_percent = 90
        db.commit()

        compute_subject_analysis(db, paper.subject_id)

        # ---------------- STAGE 5: COMPLETION ----------------
        if flagged_count > 0:
            job.status = AnalysisJobStatus.FLAGGED_REVIEW
            job.stage = f"Completed with {flagged_count} question(s) flagged for admin review"
        else:
            job.status = AnalysisJobStatus.COMPLETED
            job.stage = "Analysis complete. All questions verified."

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
