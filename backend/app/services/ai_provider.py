"""AI provider interfaces and implementations for PYQVERSE question classification and similarity."""

from __future__ import annotations

import abc
import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.models.analysis import RepeatCategory

logger = logging.getLogger(__name__)

# Bloom's Taxonomy action verbs
BLOOM_KEYWORDS = {
    "REMEMBER": [
        "define", "list", "state", "name", "identify", "recall", "mention", "what is", "who", "when"
    ],
    "UNDERSTAND": [
        "explain", "describe", "discuss", "classify", "summarize", "illustrate", "distinguish", "differentiate", "compare"
    ],
    "APPLY": [
        "calculate", "compute", "solve", "determine", "apply", "demonstrate", "implement", "construct", "write a program", "write an algorithm"
    ],
    "ANALYZE": [
        "analyze", "examine", "investigate", "contrast", "categorize", "derive", "prove", "interpret"
    ],
    "EVALUATE": [
        "evaluate", "assess", "justify", "critique", "validate", "rate", "verify", "judge"
    ],
    "CREATE": [
        "design", "formulate", "develop", "devise", "generate", "synthesize", "compose"
    ],
}

QUESTION_TYPE_KEYWORDS = {
    "DERIVATION": ["derive", "derivation", "prove that", "show that", "deduce"],
    "NUMERICAL": ["calculate", "compute", "find the value", "numerical", "determine the capacitance", "resistance", "frequency"],
    "DIAGRAM": ["diagram", "neat sketch", "draw", "schematic", "architecture diagram", "flowchart"],
    "PROGRAMMING": ["program", "algorithm", "code", "function", "write a c program", "write an assembly", "pseudocode"],
    "THEORY": ["explain", "describe", "discuss", "what is", "short note", "features of", "advantages", "disadvantages"],
}


@dataclass
class QuestionClassificationResult:
    main_topic: str
    subtopic: str
    related_concepts: List[str]
    question_type: str
    difficulty: str
    bloom_taxonomy: str
    unit_number: Optional[int]
    suggested_unit_title: Optional[str]
    suggested_topic_title: Optional[str]
    confidence: float
    explanation: str
    provisional: bool = False
    model_name: str = "pyqverse-ai-v1"
    model_provider: str = "deterministic"


@dataclass
class QuestionSimilarityResult:
    similarity_score: float
    repeat_category: RepeatCategory
    explanation: str


class BaseAIProvider(abc.ABC):
    """Abstract base class for PYQ analysis AI providers."""

    @abc.abstractmethod
    def classify_question(
        self,
        question_text: str,
        marks: Optional[int],
        syllabus_units: List[Dict[str, Any]],
    ) -> QuestionClassificationResult:
        """Classify a question against syllabus units and topics."""
        pass

    @abc.abstractmethod
    def compare_questions(
        self,
        q1_text: str,
        q2_text: str,
        topic_match: bool = False,
    ) -> QuestionSimilarityResult:
        """Compare two questions and assess semantic similarity and repetition category."""
        pass


def tokenize_clean(text: str) -> List[str]:
    """Tokenize and remove common stopwords."""
    stop_words = {
        "a", "an", "the", "and", "or", "in", "of", "to", "with", "is", "are",
        "for", "on", "by", "that", "this", "from", "as", "at", "it", "which",
        "explain", "describe", "discuss", "what", "how", "write", "briefly",
        "neat", "diagram", "sketch", "state", "define"
    }
    words = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
    return [w for w in words if w not in stop_words]


def calculate_jaccard_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    set1, set2 = set(tokens1), set(tokens2)
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


def text_exact_normalized(text: str) -> str:
    return " ".join(re.findall(r"\b[a-zA-Z0-9]+\b", text.lower()))


class RuleAndKeywordAIProvider(BaseAIProvider):
    """Deterministic, zero-latency provider that relies on syllabus structure, NLP keywords, and token similarity."""

    def __init__(self, model_name: str = "pyqverse-rule-engine-v1"):
        self.model_name = model_name
        self.model_provider = "rule_keyword"

    def classify_question(
        self,
        question_text: str,
        marks: Optional[int],
        syllabus_units: List[Dict[str, Any]],
    ) -> QuestionClassificationResult:
        lower_q = question_text.lower()
        q_tokens = tokenize_clean(question_text)

        # 1. Detect Bloom's Taxonomy
        detected_bloom = "UNDERSTAND"
        for level, verbs in BLOOM_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(v)}\b", lower_q) for v in verbs):
                detected_bloom = level
                break

        # 2. Detect Question Type
        detected_type = "THEORY"
        for q_type, kws in QUESTION_TYPE_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(kw)}\b", lower_q) for kw in kws):
                detected_type = q_type
                break

        # 3. Detect Difficulty based on marks & Bloom level
        if marks is not None:
            if marks <= 4 and detected_bloom in {"REMEMBER", "UNDERSTAND"}:
                difficulty = "EASY"
            elif marks >= 9 or detected_bloom in {"EVALUATE", "CREATE", "ANALYZE"}:
                difficulty = "HARD"
            else:
                difficulty = "MEDIUM"
        else:
            if detected_bloom in {"REMEMBER"}:
                difficulty = "EASY"
            elif detected_bloom in {"ANALYZE", "EVALUATE", "CREATE"}:
                difficulty = "HARD"
            else:
                difficulty = "MEDIUM"

        # 4. Map to syllabus units & topics
        best_unit_num: Optional[int] = None
        best_unit_title: Optional[str] = None
        best_topic_title: Optional[str] = None
        best_subtopic_title: Optional[str] = None
        best_confidence: float = 0.0
        related_concepts: List[str] = []

        if syllabus_units:
            for u in syllabus_units:
                unit_num = u.get("order_index", 1)
                unit_title = u.get("title", "")
                unit_tokens = tokenize_clean(unit_title)

                # Check topics in unit
                for t in u.get("topics", []):
                    t_title = t.get("title", "")
                    t_tokens = tokenize_clean(t_title)

                    # Match score with topic
                    jaccard = calculate_jaccard_similarity(q_tokens, t_tokens)
                    token_overlap = len(set(q_tokens).intersection(set(t_tokens)))

                    score = jaccard * 0.7 + (min(token_overlap, 3) / 3.0) * 0.3
                    if score > best_confidence:
                        best_confidence = score
                        best_unit_num = unit_num
                        best_unit_title = unit_title
                        best_topic_title = t_title

                    # Check subtopics
                    for st in t.get("subtopics", []):
                        st_title = st.get("title", "")
                        st_tokens = tokenize_clean(st_title)
                        st_jaccard = calculate_jaccard_similarity(q_tokens, st_tokens)
                        if st_jaccard > 0.3:
                            related_concepts.append(st_title)

            # Cap confidence to max 0.95 for heuristic matching
            confidence = min(round(best_confidence, 2), 0.95)
            # If no good topic overlap, fallback to general unit title token overlap
            if confidence < 0.35 and syllabus_units:
                for u in syllabus_units:
                    u_sim = calculate_jaccard_similarity(q_tokens, tokenize_clean(u.get("title", "")))
                    if u_sim > confidence:
                        confidence = round(u_sim, 2)
                        best_unit_num = u.get("order_index", 1)
                        best_unit_title = u.get("title", "")
        else:
            confidence = 0.50

        # Determine provisional flag and titles
        provisional = False
        if not syllabus_units:
            provisional = True
            confidence = 0.50
            explanation = "No active syllabus found for subject. Provisional classification assigned."
            main_topic = "General Subject Topic"
            subtopic = "General Concepts"
        elif confidence < 0.65:
            provisional = True
            explanation = f"Moderate/low confidence ({confidence:.2f}) mapping to syllabus topics. Flagged for review."
            main_topic = best_topic_title or "Unmapped Topic"
            subtopic = best_subtopic_title or "Review Pending"
        else:
            explanation = f"Mapped with {confidence:.2f} confidence to unit {best_unit_num} based on topic keyword alignment."
            main_topic = best_topic_title or best_unit_title or "Core Concepts"
            subtopic = best_subtopic_title or (q_tokens[:2] and " ".join(q_tokens[:2]).title()) or "Core Concepts"

        if not related_concepts and q_tokens:
            related_concepts = [t.title() for t in q_tokens[:4]]

        return QuestionClassificationResult(
            main_topic=main_topic,
            subtopic=subtopic,
            related_concepts=related_concepts[:5],
            question_type=detected_type,
            difficulty=difficulty,
            bloom_taxonomy=detected_bloom,
            unit_number=best_unit_num,
            suggested_unit_title=best_unit_title,
            suggested_topic_title=best_topic_title,
            confidence=max(confidence, 0.20),
            explanation=explanation,
            provisional=provisional,
            model_name=self.model_name,
            model_provider=self.model_provider,
        )

    def compare_questions(
        self,
        q1_text: str,
        q2_text: str,
        topic_match: bool = False,
    ) -> QuestionSimilarityResult:
        norm1 = text_exact_normalized(q1_text)
        norm2 = text_exact_normalized(q2_text)

        # 1. Check exact match
        if norm1 == norm2:
            return QuestionSimilarityResult(
                similarity_score=1.0,
                repeat_category=RepeatCategory.EXACT_REPEAT,
                explanation="Questions have identical wording and phrasing.",
            )

        tokens1 = tokenize_clean(q1_text)
        tokens2 = tokenize_clean(q2_text)
        jaccard = calculate_jaccard_similarity(tokens1, tokens2)

        # Common prefix/character similarity ratio
        char_match_ratio = 0.0
        if len(norm1) > 0 and len(norm2) > 0:
            shorter = min(len(norm1), len(norm2))
            matched_chars = sum(1 for a, b in zip(norm1, norm2) if a == b)
            char_match_ratio = matched_chars / max(len(norm1), len(norm2))

        combined_score = round(max(jaccard, char_match_ratio * 0.8), 2)

        if combined_score >= 0.85:
            category = RepeatCategory.EXACT_REPEAT
            explanation = f"Extremely high textual overlap ({combined_score:.2f}); exact question repeat."
        elif combined_score >= 0.65:
            category = RepeatCategory.REWORDED_REPEAT
            explanation = f"High conceptual overlap ({combined_score:.2f}) with minor phrasing differences."
        elif topic_match or combined_score >= 0.40:
            category = RepeatCategory.SAME_TOPIC_DIFFERENT_QUESTION
            explanation = f"Both questions test the same topic area with distinct formulations ({combined_score:.2f})."
        else:
            category = RepeatCategory.RELATED_CONCEPT
            explanation = f"Weak concept correlation ({combined_score:.2f}); questions address different concepts."

        return QuestionSimilarityResult(
            similarity_score=combined_score,
            repeat_category=category,
            explanation=explanation,
        )


def get_ai_provider() -> BaseAIProvider:
    """Factory returning the active AI provider."""
    # We default to the robust RuleAndKeywordAIProvider for fast, deterministic, reproducible analysis.
    # If external API is configured, it can be extended here.
    return RuleAndKeywordAIProvider()
