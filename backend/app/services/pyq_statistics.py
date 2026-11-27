"""Deterministic statistical analysis and priority scoring engine for PYQVERSE.

Every number in this module is derived from persisted question records.  Missing
marks are treated as unknown (never invented), and syllabus coverage remains
pending until an official syllabus is uploaded.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.analysis import (
    QuestionClassification,
    QuestionSimilarity,
    RepeatCategory,
    SubjectAnalysisSummary,
)
from app.models.document import ExamType, QuestionPaper, UploadedDocument
from app.models.question import Question, QuestionTopicMap
from app.models.syllabus import Topic, Unit
from app.services.ai_provider import get_ai_provider, get_ai_provider_status

logger = logging.getLogger(__name__)

def slugify_topic_key(title: str) -> str:
    """Create a stable, URL-safe key for a discovered topic title."""
    normalized = re.sub(r"[^a-z0-9]+", "-", (title or "").strip().lower()).strip("-")
    return (normalized or "general-topic")[:120]


PRIORITY_LABELS = {
    "VERY_HIGH": "MUST STUDY",
    "HIGH": "HIGH PRIORITY",
    "MEDIUM": "MEDIUM PRIORITY",
    "LOW": "LOW FREQUENCY",
    "INSUFFICIENT_DATA": "INSUFFICIENT DATA",
}


def is_generic_topic(title: str) -> bool:
    """Detect the fallback bucket used when no subject keyword matched."""
    normalized = (title or "").strip()
    return normalized.startswith("General ") and normalized.endswith(" Concepts")


def calculate_topic_priority_score(
    frequency: int,
    total_marks: int,
    max_frequency: int,
    max_marks: int,
    appeared_recently: bool,
    repeat_count: int,
    total_papers: int,
) -> tuple[float, str, dict]:
    """Calculate a transparent priority score (0-100) and category."""
    if total_papers < 2:
        category = "INSUFFICIENT_DATA"
    else:
        category = "LOW"

    freq_component = (frequency / max(max_frequency, 1)) * 40.0
    marks_component = (total_marks / max(max_marks, 1)) * 30.0
    recency_component = 20.0 if appeared_recently else 5.0
    repeat_component = min(repeat_count * 5.0, 10.0)

    raw_score = freq_component + marks_component + recency_component + repeat_component
    priority_score = min(round(raw_score, 1), 100.0)

    if total_papers >= 2:
        if priority_score >= 75.0:
            category = "VERY_HIGH"
        elif priority_score >= 55.0:
            category = "HIGH"
        elif priority_score >= 35.0:
            category = "MEDIUM"
        else:
            category = "LOW"

    breakdown = {
        "frequency_score": round(freq_component, 1),
        "marks_score": round(marks_component, 1),
        "recency_score": round(recency_component, 1),
        "repeat_bonus": round(repeat_component, 1),
    }

    return priority_score, category, breakdown


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


def recompute_subject_similarities(db: Session, subject_id: UUID) -> int:
    """Rebuild repeat-detection evidence for one subject.

    Only supported matches are stored: exact repeats, reworded repeats, and
    same-topic questions with a meaningful textual overlap.  Similar wording
    alone is not promoted to an exact repeat.
    """
    rows = db.execute(
        select(Question, UploadedDocument)
        .join(UploadedDocument, Question.document_id == UploadedDocument.id)
        .where(
            UploadedDocument.subject_id == subject_id,
            UploadedDocument.active.is_(True),
        )
    ).all()
    if len(rows) < 2:
        return 0

    question_ids = [question.id for question, _document in rows]
    db.execute(
        delete(QuestionSimilarity).where(
            (QuestionSimilarity.source_question_id.in_(question_ids))
            | (QuestionSimilarity.target_question_id.in_(question_ids))
        )
    )

    classifications = {
        classification.question_id: classification
        for classification in db.scalars(
            select(QuestionClassification).where(
                QuestionClassification.question_id.in_(question_ids)
            )
        ).all()
    }

    provider = get_ai_provider()
    stored = 0
    for index, (left, left_document) in enumerate(rows):
        left_classification = classifications.get(left.id)
        left_topic = left_classification.main_topic if left_classification else None
        for right, right_document in rows[index + 1 :]:
            if left_document.id == right_document.id:
                continue
            right_classification = classifications.get(right.id)
            right_topic = right_classification.main_topic if right_classification else None
            topic_match = bool(left_topic and right_topic and left_topic == right_topic)
            result = provider.compare_questions(
                left.extracted_text, right.extracted_text, topic_match=topic_match
            )

            should_store = False
            if result.repeat_category in (
                RepeatCategory.EXACT_REPEAT,
                RepeatCategory.REWORDED_REPEAT,
            ):
                should_store = result.similarity_score >= 0.68
            elif result.repeat_category == RepeatCategory.SAME_TOPIC_DIFFERENT_QUESTION:
                should_store = topic_match and result.similarity_score >= 0.45

            if not should_store:
                continue

            source_id, target_id = sorted([left.id, right.id], key=lambda value: str(value))
            existing = db.scalar(
                select(QuestionSimilarity).where(
                    QuestionSimilarity.source_question_id == source_id,
                    QuestionSimilarity.target_question_id == target_id,
                )
            )
            if existing:
                existing.similarity_score = result.similarity_score
                existing.repeat_category = result.repeat_category
                existing.explanation = result.explanation
            else:
                db.add(
                    QuestionSimilarity(
                        source_question_id=source_id,
                        target_question_id=target_id,
                        similarity_score=result.similarity_score,
                        repeat_category=result.repeat_category,
                        explanation=result.explanation,
                    )
                )
            stored += 1

    db.commit()
    return stored


def _load_papers(db: Session, subject_id: UUID) -> List[tuple[QuestionPaper, UploadedDocument]]:
    return db.execute(
        select(QuestionPaper, UploadedDocument)
        .join(UploadedDocument, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .where(
            QuestionPaper.subject_id == subject_id,
            UploadedDocument.active.is_(True),
        )
        .order_by(QuestionPaper.examination_year.desc().nullslast())
    ).all()


def compute_subject_analysis(db: Session, subject_id: UUID) -> SubjectAnalysisSummary:
    """Compute deterministic analytics for a subject from actual question rows."""
    papers = _load_papers(db, subject_id)
    total_papers = len(papers)
    current_year = datetime.now(timezone.utc).year
    paper_ids = [paper.id for paper, _document in papers]
    doc_ids = [document.id for _paper, document in papers]

    if not doc_ids:
        summary = db.scalar(
            select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
        )
        empty_recommendations = {
            "study_first": [],
            "frequent_repeats": [],
            "revision_order": [],
            "coverage_gaps": [],
            "insufficient_data": True,
            "syllabus_status": "PENDING",
            "ai_provider": get_ai_provider_status(),
            "data_notes": ["No active question papers are available for this subject."],
        }
        if not summary:
            summary = SubjectAnalysisSummary(
                subject_id=subject_id,
                total_papers=0,
                total_questions=0,
                coverage_score=0.0,
                unit_stats=[],
                topic_insights=[],
                repeated_question_clusters=[],
                recommendations=empty_recommendations,
            )
            db.add(summary)
        else:
            summary.total_papers = 0
            summary.total_questions = 0
            summary.coverage_score = 0.0
            summary.unit_stats = []
            summary.topic_insights = []
            summary.repeated_question_clusters = []
            summary.recommendations = empty_recommendations
            summary.calculated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(summary)
        return summary

    paper_by_doc = {document.id: (paper, document) for paper, document in papers}
    question_rows = db.execute(
        select(Question, UploadedDocument, QuestionPaper)
        .join(UploadedDocument, Question.document_id == UploadedDocument.id)
        .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
        .where(Question.document_id.in_(doc_ids))
        .order_by(Question.document_id, Question.sequence)
    ).all()

    total_questions = len(question_rows)
    question_ids = [question.id for question, _document, _paper in question_rows]

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

    units = (
        db.scalars(
            select(Unit)
            .where(Unit.subject_id == subject_id, Unit.active.is_(True))
            .order_by(Unit.order_index.asc())
        ).all()
    )
    topics_by_unit: Dict[UUID, List[Topic]] = {}
    for unit in units:
        topics_by_unit[unit.id] = db.scalars(
            select(Topic).where(Topic.unit_id == unit.id).order_by(Topic.order_index.asc())
        ).all()

    # Repeat evidence is counted from persisted similarity records.
    repeat_counts: Dict[UUID, int] = {}
    similarity_rows: List[QuestionSimilarity] = []
    if question_ids:
        similarity_rows = db.scalars(
            select(QuestionSimilarity).where(
                QuestionSimilarity.source_question_id.in_(question_ids),
                QuestionSimilarity.repeat_category.in_(
                    [RepeatCategory.EXACT_REPEAT, RepeatCategory.REWORDED_REPEAT]
                ),
            )
        ).all()
        for similarity in similarity_rows:
            repeat_counts[similarity.source_question_id] = (
                repeat_counts.get(similarity.source_question_id, 0) + 1
            )
            repeat_counts[similarity.target_question_id] = (
                repeat_counts.get(similarity.target_question_id, 0) + 1
            )

    topic_aggregates: Dict[str, Dict[str, Any]] = {}
    unit_question_counts: Counter = Counter()
    unit_marks: Counter = Counter()
    known_marks_total = 0

    for question, document, paper in question_rows:
        classification = classifications.get(question.id)
        topic_title = (
            (classification.main_topic if classification else None)
            or "Unclassified / Provisional"
        )
        marks = question.marks
        if marks is not None:
            known_marks_total += marks

        aggregate = topic_aggregates.setdefault(
            topic_title,
            {
                "topic_title": topic_title,
                "unit_number": classification.unit_number if classification else None,
                "frequency": 0,
                "questions_with_marks": 0,
                "total_marks": 0,
                "years": set(),
                "cie_count": 0,
                "see_count": 0,
                "repeat_count": 0,
                "paper_ids": set(),
                "paper_refs": [],
                "sample_questions": [],
                "question_types": Counter(),
                "difficulties": Counter(),
                "bloom_levels": Counter(),
                "marks_distribution": Counter(),
                "related_concepts": set(),
                "provisional": bool(classification.provisional) if classification else True,
            },
        )
        aggregate["frequency"] += 1
        if marks is not None:
            aggregate["questions_with_marks"] += 1
            aggregate["total_marks"] += marks
            aggregate["marks_distribution"][str(marks)] += 1
        if paper.examination_year:
            aggregate["years"].add(paper.examination_year)
        if paper.exam_type == ExamType.CIE:
            aggregate["cie_count"] += 1
        elif paper.exam_type == ExamType.SEE:
            aggregate["see_count"] += 1
        aggregate["repeat_count"] += repeat_counts.get(question.id, 0)
        aggregate["paper_ids"].add(paper.id)
        if paper.id not in {ref["paper_id"] for ref in aggregate["paper_refs"]}:
            aggregate["paper_refs"].append(_paper_ref(paper, document))
        if classification:
            if classification.question_type:
                aggregate["question_types"][classification.question_type] += 1
            if classification.difficulty:
                aggregate["difficulties"][classification.difficulty] += 1
            if classification.bloom_taxonomy:
                aggregate["bloom_levels"][classification.bloom_taxonomy] += 1
            for concept in classification.related_concepts or []:
                aggregate["related_concepts"].add(str(concept))
        if len(aggregate["sample_questions"]) < 8:
            aggregate["sample_questions"].append(
                {
                    "question_id": str(question.id),
                    "question_number": question.question_number,
                    "text": question.extracted_text,
                    "marks": marks,
                    "year": paper.examination_year,
                    "exam_type": paper.exam_type.value if paper.exam_type else None,
                    "paper_id": str(paper.id),
                    "paper_title": paper.title or document.original_filename,
                    "page_number": question.original_page_number,
                }
            )

        unit_number = classification.unit_number if classification and classification.unit_number else None
        if unit_number is not None:
            unit_question_counts[unit_number] += 1
            if marks is not None:
                unit_marks[unit_number] += marks

    max_frequency = max((item["frequency"] for item in topic_aggregates.values()), default=1)
    max_marks = max((item["total_marks"] for item in topic_aggregates.values()), default=1)

    topic_insights: List[Dict[str, Any]] = []
    for topic_name, data in topic_aggregates.items():
        years = sorted(data["years"], reverse=True)
        appeared_recently = bool(years and years[0] >= (current_year - 2))
        score, category, breakdown = calculate_topic_priority_score(
            frequency=data["frequency"],
            total_marks=data["total_marks"],
            max_frequency=max_frequency,
            max_marks=max_marks,
            appeared_recently=appeared_recently,
            repeat_count=data["repeat_count"],
            total_papers=total_papers,
        )
        generic_topic = is_generic_topic(topic_name)
        if generic_topic:
            score = 0.0
            category = "INSUFFICIENT_DATA"
        papers_appeared = len(data["paper_ids"])
        why_important = (
            f"Appeared in {papers_appeared} of {total_papers} analysed paper(s), "
            f"{data['frequency']} question(s)"
        )
        if generic_topic:
            why_important = (
                f"{data['frequency']} question(s) had no strong subject keyword match. "
                "They are grouped in this unclassified provisional bucket and are not used as a priority signal."
            )
        if data["questions_with_marks"]:
            why_important += f", {data['total_marks']} known marks across {data['questions_with_marks']} question(s)"
        if data["repeat_count"]:
            why_important += f", {data['repeat_count']} repeat link(s)"
        if years:
            why_important += f". Most recent appearance: {years[0]}."
        why_important += " This is a historical priority signal, not a prediction."

        topic_insights.append(
            {
                "topic_key": slugify_topic_key(topic_name),
                "topic_title": topic_name,
                "unit_number": data["unit_number"],
                "frequency": data["frequency"],
                "papers_appeared": papers_appeared,
                "questions_with_marks": data["questions_with_marks"],
                "total_marks": data["total_marks"],
                "last_appeared_year": years[0] if years else None,
                "years_appeared": years,
                "cie_frequency": data["cie_count"],
                "see_frequency": data["see_count"],
                "repeat_count": data["repeat_count"],
                "priority_score": score,
                "priority_category": category,
                "priority_label": "UNCLASSIFIED" if generic_topic else PRIORITY_LABELS.get(category, category),
                "score_breakdown": breakdown,
                "why_important": why_important,
                "provisional": data["provisional"],
                "question_type_distribution": dict(data["question_types"]),
                "difficulty_distribution": dict(data["difficulties"]),
                "bloom_distribution": dict(data["bloom_levels"]),
                "marks_distribution": dict(data["marks_distribution"]),
                "related_concepts": sorted(data["related_concepts"])[:8],
                "papers": data["paper_refs"],
                "sample_questions": data["sample_questions"],
            }
        )

    topic_insights.sort(key=lambda item: (item["priority_score"], item["frequency"]), reverse=True)

    # Unit stats are only produced when an official syllabus exists.
    unit_stats: List[Dict[str, Any]] = []
    if units:
        total_known_marks = sum(unit_marks.values()) or 1
        for unit in units:
            question_count = unit_question_counts.get(unit.order_index, 0)
            marks = unit_marks.get(unit.order_index, 0)
            unit_stats.append(
                {
                    "unit_id": str(unit.id),
                    "unit_number": unit.order_index,
                    "title": unit.title,
                    "question_count": question_count,
                    "total_marks": marks,
                    "marks_percentage": round((marks / total_known_marks) * 100, 1),
                }
            )

    # Repeated-question clusters with paper references.
    clusters: List[Dict[str, Any]] = []
    if question_ids:
        rows = db.execute(
            select(QuestionSimilarity, Question)
            .join(Question, QuestionSimilarity.target_question_id == Question.id)
            .where(
                QuestionSimilarity.source_question_id.in_(question_ids),
                QuestionSimilarity.similarity_score >= 0.45,
            )
            .order_by(QuestionSimilarity.similarity_score.desc())
        ).all()
        seen_pairs = set()
        for similarity, target_question in rows:
            pair_key = tuple(
                sorted([str(similarity.source_question_id), str(similarity.target_question_id)])
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            source_question = db.get(Question, similarity.source_question_id)
            if not source_question:
                continue
            source_paper_doc = paper_by_doc.get(source_question.document_id)
            target_paper_doc = paper_by_doc.get(target_question.document_id)
            if not source_paper_doc or not target_paper_doc:
                continue
            source_paper, source_doc = source_paper_doc
            target_paper, target_doc = target_paper_doc
            source_classification = classifications.get(source_question.id)
            target_classification = classifications.get(target_question.id)
            clusters.append(
                {
                    "source_id": str(source_question.id),
                    "source_text": source_question.extracted_text,
                    "source_marks": source_question.marks,
                    "source_question_number": source_question.question_number,
                    "source_topic": source_classification.main_topic if source_classification else None,
                    "source_paper": _paper_ref(source_paper, source_doc),
                    "target_id": str(target_question.id),
                    "target_text": target_question.extracted_text,
                    "target_marks": target_question.marks,
                    "target_question_number": target_question.question_number,
                    "target_topic": target_classification.main_topic if target_classification else None,
                    "target_paper": _paper_ref(target_paper, target_doc),
                    "similarity_score": similarity.similarity_score,
                    "repeat_category": similarity.repeat_category.value,
                    "explanation": similarity.explanation,
                }
            )

    # Syllabus coverage is explicitly pending when no official syllabus exists.
    syllabus_status = "AVAILABLE" if units else "PENDING"
    coverage_gaps: List[Dict[str, Any]] = []
    coverage_score = 0.0
    if units:
        covered_titles = {item["topic_title"].lower() for item in topic_insights}
        all_syllabus_topics = 0
        for unit in units:
            for topic in topics_by_unit.get(unit.id, []):
                all_syllabus_topics += 1
                if topic.title.lower() not in covered_titles:
                    coverage_gaps.append(
                        {
                            "unit_number": unit.order_index,
                            "unit_title": unit.title,
                            "topic_title": topic.title,
                        }
                    )
        if all_syllabus_topics:
            coverage_score = round(
                ((all_syllabus_topics - len(coverage_gaps)) / all_syllabus_topics) * 100, 1
            )

    study_first = [
        {
            "topic_title": item["topic_title"],
            "unit_number": item["unit_number"],
            "priority_score": item["priority_score"],
            "priority_label": item["priority_label"],
        }
        for item in topic_insights[:5]
    ]
    frequent_repeats = [
        {
            "text": cluster["source_text"],
            "marks": cluster["source_marks"],
            "similarity": cluster["similarity_score"],
            "repeat_category": cluster["repeat_category"],
        }
        for cluster in clusters[:5]
    ]
    revision_order = [
        {
            "topic_title": item["topic_title"],
            "unit_number": item["unit_number"],
            "rank": index + 1,
        }
        for index, item in enumerate(topic_insights)
    ]

    data_notes: List[str] = []
    if syllabus_status == "PENDING":
        data_notes.append(
            "No official syllabus is uploaded. Topics are AI-discovered/provisional and syllabus coverage is pending."
        )
    if known_marks_total == 0 and total_questions:
        data_notes.append(
            "Marks could not be read from these PDFs; marks-based statistics only include values that were extracted."
        )

    recommendations = {
        "study_first": study_first,
        "frequent_repeats": frequent_repeats,
        "revision_order": revision_order,
        "coverage_gaps": coverage_gaps[:20],
        "insufficient_data": total_papers < 2,
        "syllabus_status": syllabus_status,
        "ai_provider": get_ai_provider_status(),
        "data_notes": data_notes,
    }

    summary = db.scalar(
        select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
    )
    if not summary:
        summary = SubjectAnalysisSummary(
            subject_id=subject_id,
            total_papers=total_papers,
            total_questions=total_questions,
            coverage_score=coverage_score,
            unit_stats=unit_stats,
            topic_insights=topic_insights,
            repeated_question_clusters=clusters,
            recommendations=recommendations,
        )
        db.add(summary)
    else:
        summary.total_papers = total_papers
        summary.total_questions = total_questions
        summary.coverage_score = coverage_score
        summary.unit_stats = unit_stats
        summary.topic_insights = topic_insights
        summary.repeated_question_clusters = clusters
        summary.recommendations = recommendations
        summary.calculated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(summary)
    return summary
