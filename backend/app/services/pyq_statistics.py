"""Deterministic statistical analysis and priority scoring engine for PYQVERSE."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.academic import Subject
from app.models.analysis import QuestionClassification, QuestionSimilarity, RepeatCategory, SubjectAnalysisSummary
from app.models.document import ExamType, QuestionPaper, UploadedDocument
from app.models.question import Question, QuestionTopicMap
from app.models.syllabus import Topic, Unit, VerificationStatus

logger = logging.getLogger(__name__)


def calculate_topic_priority_score(
    frequency: int,
    total_marks: int,
    max_frequency: int,
    max_marks: int,
    appeared_recently: bool,
    repeat_count: int,
    total_papers: int,
) -> tuple[float, str, dict]:
    """Calculate transparent priority score (0-100) and priority category."""
    if total_papers < 2:
        category = "INSUFFICIENT_DATA"
    else:
        category = "LOW"

    # Normalized components
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


def compute_subject_analysis(db: Session, subject_id: UUID) -> SubjectAnalysisSummary:
    """Compute deterministic analytics for a subject across all active question papers."""
    # 1. Fetch active question papers
    papers = (
        db.execute(
            select(QuestionPaper, UploadedDocument)
            .join(UploadedDocument, QuestionPaper.uploaded_document_id == UploadedDocument.id)
            .where(
                QuestionPaper.subject_id == subject_id,
                UploadedDocument.active.is_(True),
            )
            .order_by(QuestionPaper.examination_year.desc().nullslast())
        )
        .all()
    )

    total_papers = len(papers)
    current_year = datetime.now(timezone.utc).year
    paper_ids = [p[0].id for p in papers]
    doc_ids = [p[1].id for p in papers]

    if not doc_ids:
        # No papers uploaded yet for this subject
        summary = db.scalar(
            select(SubjectAnalysisSummary).where(SubjectAnalysisSummary.subject_id == subject_id)
        )
        if not summary:
            summary = SubjectAnalysisSummary(
                subject_id=subject_id,
                total_papers=0,
                total_questions=0,
                coverage_score=0.0,
                unit_stats=[],
                topic_insights=[],
                repeated_question_clusters=[],
                recommendations={
                    "study_first": [],
                    "frequent_repeats": [],
                    "revision_order": [],
                    "coverage_gaps": [],
                    "insufficient_data": True,
                },
            )
            db.add(summary)
            db.commit()
            db.refresh(summary)
        return summary

    # 2. Fetch all questions for these documents
    questions = (
        db.execute(
            select(Question, UploadedDocument.exam_type, QuestionPaper.examination_year)
            .join(UploadedDocument, Question.document_id == UploadedDocument.id)
            .join(QuestionPaper, QuestionPaper.uploaded_document_id == UploadedDocument.id)
            .where(Question.document_id.in_(doc_ids))
        )
        .all()
    )

    total_questions = len(questions)
    question_ids = [q[0].id for q in questions]

    # 3. Fetch classifications
    classifications = {}
    if question_ids:
        cl_rows = db.scalars(
            select(QuestionClassification).where(QuestionClassification.question_id.in_(question_ids))
        ).all()
        for cl in cl_rows:
            classifications[cl.question_id] = cl

    # 4. Fetch unit and topic data
    units = (
        db.scalars(
            select(Unit)
            .where(Unit.subject_id == subject_id, Unit.active.is_(True))
            .order_by(Unit.order_index.asc())
        )
        .all()
    )

    topics_by_unit: Dict[UUID, List[Topic]] = {}
    topic_map: Dict[UUID, Topic] = {}
    for u in units:
        t_list = db.scalars(
            select(Topic).where(Topic.unit_id == u.id).order_by(Topic.order_index.asc())
        ).all()
        topics_by_unit[u.id] = t_list
        for t in t_list:
            topic_map[t.id] = t

    # 5. Fetch question-topic mappings
    q_topic_mappings = []
    if question_ids:
        q_topic_mappings = db.execute(
            select(QuestionTopicMap.question_id, QuestionTopicMap.topic_id, QuestionTopicMap.confidence)
            .where(QuestionTopicMap.question_id.in_(question_ids))
        ).all()

    question_to_topics: Dict[UUID, List[UUID]] = {}
    for q_id, t_id, _conf in q_topic_mappings:
        question_to_topics.setdefault(q_id, []).append(t_id)

    # 6. Aggregate Unit Stats
    unit_stats: List[Dict[str, Any]] = []
    unit_q_counts: Dict[int, int] = {}
    unit_marks: Dict[int, int] = {}

    for q, exam_type, exam_year in questions:
        cl = classifications.get(q.id)
        u_num = cl.unit_number if cl and cl.unit_number else 1
        q_marks = q.marks or 5
        unit_q_counts[u_num] = unit_q_counts.get(u_num, 0) + 1
        unit_marks[u_num] = unit_marks.get(u_num, 0) + q_marks

    total_marks_all = sum(unit_marks.values()) or 1

    for idx, u in enumerate(units):
        u_num = u.order_index
        q_count = unit_q_counts.get(u_num, 0)
        u_m = unit_marks.get(u_num, 0)
        pct = round((u_m / total_marks_all) * 100, 1)

        unit_stats.append({
            "unit_id": str(u.id),
            "unit_number": u_num,
            "title": u.title,
            "question_count": q_count,
            "total_marks": u_m,
            "marks_percentage": pct,
        })

    # If no units defined in database, synthesize from classifications
    if not units and unit_q_counts:
        for u_num, q_count in sorted(unit_q_counts.items()):
            u_m = unit_marks.get(u_num, 0)
            unit_stats.append({
                "unit_id": None,
                "unit_number": u_num,
                "title": f"Unit {u_num}",
                "question_count": q_count,
                "total_marks": u_m,
                "marks_percentage": round((u_m / total_marks_all) * 100, 1),
            })

    # 7. Topic Insights
    topic_aggregates: Dict[str, Dict[str, Any]] = {}
    # Count repeats per question
    repeat_counts: Dict[UUID, int] = {}
    if question_ids:
        sim_rows = db.scalars(
            select(QuestionSimilarity).where(
                QuestionSimilarity.source_question_id.in_(question_ids),
                QuestionSimilarity.repeat_category.in_([RepeatCategory.EXACT_REPEAT, RepeatCategory.REWORDED_REPEAT]),
            )
        ).all()
        for s in sim_rows:
            repeat_counts[s.source_question_id] = repeat_counts.get(s.source_question_id, 0) + 1
            repeat_counts[s.target_question_id] = repeat_counts.get(s.target_question_id, 0) + 1

    for q, exam_type, exam_year in questions:
        cl = classifications.get(q.id)
        topic_title = (cl.main_topic if cl and cl.main_topic else None) or "General Topic"
        q_marks = q.marks or 5

        if topic_title not in topic_aggregates:
            topic_aggregates[topic_title] = {
                "topic_title": topic_title,
                "unit_number": cl.unit_number if cl else 1,
                "frequency": 0,
                "total_marks": 0,
                "years": set(),
                "cie_count": 0,
                "see_count": 0,
                "repeat_count": 0,
                "sample_questions": [],
            }

        entry = topic_aggregates[topic_title]
        entry["frequency"] += 1
        entry["total_marks"] += q_marks
        if exam_year:
            entry["years"].add(exam_year)
        if exam_type == ExamType.CIE:
            entry["cie_count"] += 1
        else:
            entry["see_count"] += 1
        entry["repeat_count"] += repeat_counts.get(q.id, 0)
        if len(entry["sample_questions"]) < 3:
            entry["sample_questions"].append({
                "question_number": q.question_number,
                "text": q.extracted_text,
                "marks": q.marks,
                "year": exam_year,
            })

    # Compute priority scores for topics
    max_freq = max((t["frequency"] for t in topic_aggregates.values()), default=1)
    max_m = max((t["total_marks"] for t in topic_aggregates.values()), default=1)

    topic_insights: List[Dict[str, Any]] = []
    for topic_name, data in topic_aggregates.items():
        years = sorted(list(data["years"]), reverse=True)
        appeared_recently = bool(years and years[0] >= (current_year - 2))

        score, category, breakdown = calculate_topic_priority_score(
            frequency=data["frequency"],
            total_marks=data["total_marks"],
            max_frequency=max_freq,
            max_marks=max_m,
            appeared_recently=appeared_recently,
            repeat_count=data["repeat_count"],
            total_papers=total_papers,
        )

        topic_insights.append({
            "topic_title": topic_name,
            "unit_number": data["unit_number"],
            "frequency": data["frequency"],
            "total_marks": data["total_marks"],
            "last_appeared_year": years[0] if years else None,
            "years_appeared": years,
            "cie_frequency": data["cie_count"],
            "see_frequency": data["see_count"],
            "priority_score": score,
            "priority_category": category,
            "score_breakdown": breakdown,
            "sample_questions": data["sample_questions"],
        })

    # Sort topics by priority score descending
    topic_insights.sort(key=lambda t: t["priority_score"], reverse=True)

    # 8. Repeated Question Clusters
    clusters: List[Dict[str, Any]] = []
    if question_ids:
        repeated_sims = (
            db.execute(
                select(QuestionSimilarity, Question)
                .join(Question, QuestionSimilarity.target_question_id == Question.id)
                .where(
                    QuestionSimilarity.source_question_id.in_(question_ids),
                    QuestionSimilarity.similarity_score >= 0.70,
                )
                .order_by(QuestionSimilarity.similarity_score.desc())
                .limit(20)
            )
            .all()
        )

        seen_pairs = set()
        for sim, target_q in repeated_sims:
            pair_key = tuple(sorted([str(sim.source_question_id), str(sim.target_question_id)]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            source_q = db.get(Question, sim.source_question_id)
            if not source_q:
                continue

            clusters.append({
                "source_id": str(source_q.id),
                "source_text": source_q.extracted_text,
                "source_marks": source_q.marks,
                "target_id": str(target_q.id),
                "target_text": target_q.extracted_text,
                "target_marks": target_q.marks,
                "similarity_score": sim.similarity_score,
                "repeat_category": sim.repeat_category.value,
                "explanation": sim.explanation,
            })

    # 9. Recommendations & Syllabus Coverage
    # Syllabus coverage gaps: syllabus topics not covered in any questions
    covered_topic_titles = {t["topic_title"].lower() for t in topic_insights}
    coverage_gaps: List[Dict[str, Any]] = []

    for u in units:
        for t in topics_by_unit.get(u.id, []):
            if t.title.lower() not in covered_topic_titles:
                coverage_gaps.append({
                    "unit_number": u.order_index,
                    "unit_title": u.title,
                    "topic_title": t.title,
                })

    # Coverage score: percentage of syllabus topics covered
    all_syllabus_topic_count = sum(len(tl) for tl in topics_by_unit.values())
    if all_syllabus_topic_count > 0:
        coverage_score = round(
            ((all_syllabus_topic_count - len(coverage_gaps)) / all_syllabus_topic_count) * 100, 1
        )
    else:
        coverage_score = 50.0 if total_questions > 0 else 0.0

    study_first = [
        {"topic_title": t["topic_title"], "unit_number": t["unit_number"], "priority_score": t["priority_score"]}
        for t in topic_insights[:4]
    ]

    frequent_repeats = [
        {"text": c["source_text"], "marks": c["source_marks"], "similarity": c["similarity_score"]}
        for c in clusters[:5]
    ]

    revision_order = [
        {"topic_title": t["topic_title"], "unit_number": t["unit_number"], "rank": i + 1}
        for i, t in enumerate(topic_insights)
    ]

    recommendations = {
        "study_first": study_first,
        "frequent_repeats": frequent_repeats,
        "revision_order": revision_order,
        "coverage_gaps": coverage_gaps[:10],
        "insufficient_data": total_papers < 2,
    }

    # 10. Persist or update SubjectAnalysisSummary
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
