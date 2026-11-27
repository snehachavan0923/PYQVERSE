"""AI provider interfaces and deterministic fallbacks for PYQVERSE.

No external LLM is required for the platform to function.  When no provider is
configured the rule/keyword engine performs question classification, provisional
topic discovery and repeat detection.  Every result records the actual provider
used; we never pretend an LLM was called.
"""

from __future__ import annotations

import abc
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.models.analysis import RepeatCategory

logger = logging.getLogger(__name__)

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
    "DIAGRAM": ["diagram", "neat sketch", "draw", "schematic", "architecture diagram", "flowchart", "gantt"],
    "PROGRAMMING": ["program", "algorithm", "code", "function", "write a c program", "write an assembly", "pseudocode"],
    "THEORY": ["explain", "describe", "discuss", "what is", "short note", "features of", "advantages", "disadvantages"],
}

# Provisional topic discovery rules.  These are deliberately labelled as
# AI-discovered/provisional because no official syllabus is available yet.
SUBJECT_TOPIC_RULES: Dict[str, List[Tuple[str, List[str]]]] = {
    "CS233": [
        ("Arrays & Strings", ["array", "string", "matrix", "sparse matrix", "polynomial"]),
        ("Stacks", ["stack", "push", "pop", "infix", "postfix", "prefix", "parenthesis"]),
        ("Queues", ["queue", "enqueue", "dequeue", "circular queue", "deque", "priority queue"]),
        ("Linked Lists", ["linked list", "singly linked", "doubly linked", "circular linked", "node", "head pointer"]),
        ("Trees", ["tree", "binary tree", "bst", "binary search tree", "traversal", "inorder", "preorder", "postorder", "avl", "heap", "threaded"]),
        ("Graphs", ["graph", "bfs", "dfs", "dijkstra", "spanning tree", "kruskal", "prim", "topological", "adjacency"]),
        ("Hashing", ["hash", "hashing", "collision", "chaining", "probing"]),
        ("Sorting", ["sort", "quicksort", "merge sort", "bubble sort", "insertion sort", "selection sort", "heap sort", "radix sort"]),
        ("Searching", ["search", "binary search", "linear search"]),
        ("Recursion", ["recursion", "recursive", "tower of hanoi", "factorial", "fibonacci"]),
        ("Algorithm Analysis", ["complexity", "big-o", "time complexity", "space complexity", "asymptotic"]),
    ],
    "CS234": [
        ("Number Systems & Binary Arithmetic", ["binary", "2's complement", "twos complement", "booth", "floating point", "overflow", "bcd", "gray code", "hexadecimal", "octal", "ieee", "single precision", "excess-3"]),
        ("Boolean Algebra & Logic Minimization", ["boolean", "k-map", "karnaugh", "prime implicant", "sop", "pos", "truth table", "logic expression", "don't care", "simplification", "quine-mccluskey"]),
        ("Combinational Logic Circuits", ["multiplexer", "mux", "decoder", "encoder", "adder", "subtractor", "comparator", "parity", "combinational", "ripple carry", "look-ahead", "half adder", "full adder"]),
        ("Sequential Logic & Flip-Flops", ["flip-flop", "flip flop", "latch", "counter", "register", "state machine", "sequential", "jk flip", "sr flip", "d flip", "t flip", "ripple counter"]),
        ("Memory & Programmable Logic", ["memory", "ram", "rom", "prom", "pla", "pal", "cache", "sram", "dram"]),
        ("Computer Organization & CPU", ["instruction", "addressing mode", "cpu", "alu", "control unit", "datapath", "pipelining", "pipeline", "bus", "register transfer", "microoperation", "microprogram", "control sequence", "hardwired", "instruction cycle"]),
        ("I/O, Interrupts & DMA", ["interrupt", "dma", "i/o", "peripheral", "device"]),
    ],
    "CS235": [
        ("Process Management", ["process", "thread", "scheduling", "context switch", "fork", "pid", "zombie", "orphan", "process state", "round robin", "sjf", "fcfs"]),
        ("Synchronization & Deadlocks", ["synchronization", "semaphore", "mutex", "critical section", "deadlock", "banker", "wait-for", "race condition", "monitor", "spinlock", "peterson"]),
        ("Memory Management", ["memory", "paging", "segmentation", "virtual memory", "page replacement", "frame", "thrashing", "lru", "fifo", "demand paging", "address space"]),
        ("File Systems", ["file system", "file allocation", "directory", "inode", "disk scheduling", "fat", "linked allocation", "indexed allocation", "contiguous allocation"]),
        ("I/O & Storage", ["i/o", "device driver", "interrupt", "dma", "buffering", "disk", "raid", "cache"]),
        ("OS Structures & Protection", ["kernel", "system call", "monolithic", "microkernel", "user mode", "kernel mode", "virtual machine", "protection", "security"]),
    ],
    "MA231": [
        ("Matrices & Linear Systems", ["matrix", "matrices", "determinant", "rank", "gaussian", "inverse", "linear system", "singular values", "lu decomposition"]),
        ("Vector Spaces", ["vector space", "subspace", "basis", "dimension", "linear independence", "span", "linearly independent"]),
        ("Linear Transformations", ["linear transformation", "kernel", "range", "nullity", "isomorphism", "matrix representation"]),
        ("Eigenvalues & Eigenvectors", ["eigenvalue", "eigenvector", "diagonalization", "characteristic equation", "cayley-hamilton"]),
        ("Inner Product Spaces", ["inner product", "orthogonal", "gram-schmidt", "norm", "projection", "least squares"]),
        ("Probability", ["probability", "random variable", "distribution", "binomial", "poisson", "normal", "expectation", "variance", "bayes", "conditional"]),
        ("Statistics", ["mean", "median", "mode", "standard deviation", "correlation", "regression", "hypothesis", "chi-square", "t-test", "confidence interval"]),
        ("Numerical Methods", ["newton", "interpolation", "numerical integration", "trapezoidal", "simpson", "rayleigh", "power method"]),
    ],
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
    model_name: str = "pyqverse-rule-engine-v1"
    model_provider: str = "rule_keyword"


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
        subject_code: Optional[str] = None,
        subject_name: Optional[str] = None,
    ) -> QuestionClassificationResult:
        """Classify a question against syllabus units and/or provisional topics."""
        pass

    @abc.abstractmethod
    def compare_questions(
        self,
        q1_text: str,
        q2_text: str,
        topic_match: bool = False,
    ) -> QuestionSimilarityResult:
        """Compare two questions and assess similarity and repetition category."""
        pass


def tokenize_clean(text: str) -> List[str]:
    """Tokenize and remove common stopwords."""
    stop_words = {
        "a", "an", "the", "and", "or", "in", "of", "to", "with", "is", "are",
        "for", "on", "by", "that", "this", "from", "as", "at", "it", "which",
        "explain", "describe", "discuss", "what", "how", "write", "briefly",
        "neat", "diagram", "sketch", "state", "define", "differentiate",
        "compare", "list", "give", "example", "examples", "using", "use",
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


def _subject_rules(subject_code: Optional[str]) -> List[Tuple[str, List[str]]]:
    if not subject_code:
        return []
    code = subject_code.upper()
    for prefix, rules in SUBJECT_TOPIC_RULES.items():
        if code.startswith(prefix):
            return rules
    return []


def _keyword_present(text: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", text) is not None


def discover_provisional_topic(
    question_text: str,
    subject_code: Optional[str] = None,
    subject_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically discover a provisional topic from question keywords."""
    lowered = question_text.lower()
    rules = _subject_rules(subject_code)
    best_topic: Optional[str] = None
    best_hits: List[str] = []
    best_score = 0

    for topic, keywords in rules:
        hits = [kw for kw in keywords if _keyword_present(lowered, kw)]
        score = len(hits)
        if score > best_score:
            best_score = score
            best_topic = topic
            best_hits = hits

    if best_topic and best_score > 0:
        subtopic = best_hits[0].title()
        related = [hit.title() for hit in best_hits[1:5]]
        confidence = min(round(0.55 + best_score * 0.05, 2), 0.78)
        return {
            "main_topic": best_topic,
            "subtopic": subtopic,
            "related_concepts": related,
            "confidence": confidence,
            "explanation": (
                f"Provisional topic discovered from {best_score} question keyword(s). "
                "No official syllabus is available, so this is an AI-discovered topic, not a verified unit mapping."
            ),
        }

    fallback_topic = (
        f"General {subject_name} Concepts" if subject_name else "General Concepts"
    )
    tokens = tokenize_clean(question_text)
    related = [token.title() for token in tokens[:4]]
    return {
        "main_topic": fallback_topic,
        "subtopic": "Provisional concept",
        "related_concepts": related,
        "confidence": 0.3,
        "explanation": (
            "No syllabus or strong topic keyword match was found. The question is grouped "
            "under a provisional general topic and should be reviewed when a syllabus is uploaded."
        ),
    }


class RuleAndKeywordAIProvider(BaseAIProvider):
    """Deterministic provider using syllabus structure, NLP keywords and token similarity."""

    def __init__(self, model_name: str = "pyqverse-rule-engine-v1"):
        self.model_name = model_name
        self.model_provider = "rule_keyword"
        self.ai_available = bool(settings.AI_API_KEY.strip())
        self.mode = "rule_keyword"

    def classify_question(
        self,
        question_text: str,
        marks: Optional[int],
        syllabus_units: List[Dict[str, Any]],
        subject_code: Optional[str] = None,
        subject_name: Optional[str] = None,
    ) -> QuestionClassificationResult:
        lower_q = question_text.lower()
        q_tokens = tokenize_clean(question_text)

        detected_bloom = "UNDERSTAND"
        for level, verbs in BLOOM_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(v)}\b", lower_q) for v in verbs):
                detected_bloom = level
                break

        detected_type = "THEORY"
        for q_type, kws in QUESTION_TYPE_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(kw)}\b", lower_q) for kw in kws):
                detected_type = q_type
                break

        if marks is not None:
            if marks <= 4 and detected_bloom in {"REMEMBER", "UNDERSTAND"}:
                difficulty = "EASY"
            elif marks >= 9 or detected_bloom in {"EVALUATE", "CREATE", "ANALYZE"}:
                difficulty = "HARD"
            else:
                difficulty = "MEDIUM"
        else:
            if detected_bloom == "REMEMBER":
                difficulty = "EASY"
            elif detected_bloom in {"ANALYZE", "EVALUATE", "CREATE"}:
                difficulty = "HARD"
            else:
                difficulty = "MEDIUM"

        best_unit_num: Optional[int] = None
        best_unit_title: Optional[str] = None
        best_topic_title: Optional[str] = None
        best_confidence: float = 0.0
        related_concepts: List[str] = []

        if syllabus_units:
            for unit in syllabus_units:
                unit_num = unit.get("order_index", 1)
                unit_title = unit.get("title", "")
                for topic in unit.get("topics", []):
                    topic_title = topic.get("title", "")
                    topic_tokens = tokenize_clean(topic_title)
                    jaccard = calculate_jaccard_similarity(q_tokens, topic_tokens)
                    token_overlap = len(set(q_tokens).intersection(set(topic_tokens)))
                    score = jaccard * 0.7 + (min(token_overlap, 3) / 3.0) * 0.3
                    if score > best_confidence:
                        best_confidence = score
                        best_unit_num = unit_num
                        best_unit_title = unit_title
                        best_topic_title = topic_title
                    for subtopic in topic.get("subtopics", []):
                        subtopic_title = subtopic.get("title", "")
                        if calculate_jaccard_similarity(q_tokens, tokenize_clean(subtopic_title)) > 0.3:
                            related_concepts.append(subtopic_title)

            if best_confidence < 0.35:
                for unit in syllabus_units:
                    unit_similarity = calculate_jaccard_similarity(
                        q_tokens, tokenize_clean(unit.get("title", ""))
                    )
                    if unit_similarity > best_confidence:
                        best_confidence = round(unit_similarity, 2)
                        best_unit_num = unit.get("order_index", 1)
                        best_unit_title = unit.get("title", "")

        if syllabus_units and best_topic_title and best_confidence >= 0.35:
            confidence = min(round(best_confidence, 2), 0.95)
            provisional = confidence < 0.65
            main_topic = best_topic_title
            subtopic = related_concepts[0] if related_concepts else "Core Concepts"
            explanation = (
                f"Mapped with {confidence:.2f} confidence to syllabus unit {best_unit_num} "
                "based on topic keyword alignment."
            )
            if provisional:
                explanation = (
                    f"Moderate/low confidence ({confidence:.2f}) mapping to syllabus topics. "
                    "Flagged for review."
                )
            if not related_concepts:
                related_concepts = [token.title() for token in q_tokens[:4]]
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
                confidence=max(confidence, 0.35),
                explanation=explanation,
                provisional=provisional,
                model_name=self.model_name,
                model_provider=self.model_provider,
            )

        discovered = discover_provisional_topic(question_text, subject_code, subject_name)
        return QuestionClassificationResult(
            main_topic=discovered["main_topic"],
            subtopic=discovered["subtopic"],
            related_concepts=discovered["related_concepts"][:5],
            question_type=detected_type,
            difficulty=difficulty,
            bloom_taxonomy=detected_bloom,
            unit_number=None,
            suggested_unit_title=None,
            suggested_topic_title=discovered["main_topic"],
            confidence=discovered["confidence"],
            explanation=discovered["explanation"],
            provisional=True,
            model_name="pyqverse-topic-discovery-v1",
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

        if norm1 and norm1 == norm2:
            return QuestionSimilarityResult(
                similarity_score=1.0,
                repeat_category=RepeatCategory.EXACT_REPEAT,
                explanation="Questions have identical normalized wording.",
            )

        tokens1 = tokenize_clean(q1_text)
        tokens2 = tokenize_clean(q2_text)
        jaccard = calculate_jaccard_similarity(tokens1, tokens2)
        sequence_ratio = SequenceMatcher(None, norm1, norm2).ratio() if norm1 and norm2 else 0.0
        combined_score = round(max(jaccard, sequence_ratio * 0.95), 2)

        if combined_score >= 0.92:
            category = RepeatCategory.EXACT_REPEAT
            explanation = f"Extremely high textual overlap ({combined_score:.2f}); exact question repeat."
        elif combined_score >= 0.68:
            category = RepeatCategory.REWORDED_REPEAT
            explanation = f"High conceptual overlap ({combined_score:.2f}) with phrasing differences."
        elif topic_match and combined_score >= 0.40:
            category = RepeatCategory.SAME_TOPIC_DIFFERENT_QUESTION
            explanation = f"Same provisional topic with a distinct question formulation ({combined_score:.2f})."
        else:
            category = RepeatCategory.RELATED_CONCEPT
            explanation = f"Weak concept correlation ({combined_score:.2f})."

        return QuestionSimilarityResult(
            similarity_score=combined_score,
            repeat_category=category,
            explanation=explanation,
        )


def get_ai_provider() -> BaseAIProvider:
    """Return the active provider.

    Only the deterministic engine is implemented today.  If an API key exists it
    is recorded by the provider status endpoint, but no LLM call is fabricated.
    """
    return RuleAndKeywordAIProvider()


def get_ai_provider_status() -> Dict[str, Any]:
    provider = get_ai_provider()
    configured = bool(settings.AI_API_KEY.strip())
    message = (
        "No external LLM call is made. Deterministic keyword/topic extraction is used."
        if not configured
        else "An AI key is configured, but this build still uses the deterministic engine for reproducibility."
    )
    return {
        "provider": provider.model_provider,
        "model_name": provider.model_name,
        "model": provider.model_name,
        "configured": configured,
        "llm_configured": configured,
        "deterministic": True,
        "notes": [message],
        "mode": "rule_keyword_fallback",
        "message": message,
    }
