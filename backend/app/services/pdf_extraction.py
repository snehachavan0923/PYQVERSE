"""PDF extraction service for PYQVERSE examination question papers.

The extractor is intentionally conservative: it keeps only text that looks like
a real examination question, preserves the printed question number where one is
available, and records the source page.  It never invents questions or marks.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

import pymupdf

logger = logging.getLogger(__name__)

MODULE_PATTERN = re.compile(
    r"(?i)^\s*(?:part|module|unit)\s*[-:]?\s*([0-9ivxlcdm]+|[a-e])\b"
)

# Question number patterns, tried in order.
HIERARCHICAL_PATTERN = re.compile(
    r"^\s*(?:Q\.?\s*)?(?P<major>\d{1,2})\s*[.\-]\s*(?P<minor>\d{1,2})\s*[.):]?\s*(?P<rest>.*)$"
)
LETTER_PATTERN = re.compile(
    r"^\s*(?:Q\.?\s*)?(?P<major>\d{1,2})\s*[.)]?\s*(?P<sub>[a-f])\s*[.)]\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
LETTER_DOT_PATTERN = re.compile(
    r"^\s*(?:Q\.?\s*)?(?P<major>\d{1,2})\s*[.)]\s*(?P<sub>[a-f])\s*[.)]?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
MAIN_PATTERN = re.compile(
    r"^\s*(?:Q\.?\s*)?(?P<major>\d{1,2})\s*[.)]\s*(?P<rest>.*)$"
)
BRACKET_MAIN_PATTERN = re.compile(r"^\s*\((?P<major>\d{1,2})\)\s*(?P<rest>.*)$")
SUB_ONLY_PATTERN = re.compile(
    r"^\s*(?:Q\.?\s*)?(?P<major>\d{1,2})\s*[.)]?\s+(?P<sub>[a-f])\s*[.)]?\s*$",
    re.IGNORECASE,
)
SUBQUESTION_PATTERN = re.compile(
    r"^\s*(?:\(?([a-f])\)|\b([a-f])\.)\s+(.+)",
    re.IGNORECASE,
)

MARKS_PATTERN = re.compile(
    r"(?:\[\s*([0-9]{1,2})\s*(?:marks?|m)?\s*\]"
    r"|\(\s*([0-9]{1,2})\s*(?:marks?|m)\s*\)"
    r"|\b([0-9]{1,2})\s*(?:marks?|m)\b)",
    re.IGNORECASE,
)
MARKS_LINE_PATTERN = re.compile(r"^\s*0?([0-9]{1,2})\s*$")
COURSE_OUTCOME_LINE_PATTERN = re.compile(r"^\s*(?:L[1-6]|CO\s?\d{1,2}|BT\s?\d)\s*$", re.IGNORECASE)

INSTRUCTION_PREFIXES = (
    "answer all",
    "answer five",
    "answer any",
    "mathematics handbook",
    "students need",
    "students should",
    "all questions",
    "note:",
    "instructions",
    "duration",
    "maximum marks",
    "academic year",
    "date",
    "staff",
    "course code",
    "semester",
    "name",
    "usn",
    "section",
)

PAGE_HEADER_PATTERNS = (
    re.compile(r"(?i)r\s*v\s*college of engineering"),
    re.compile(r"(?i)mysore road"),
    re.compile(r"(?i)vidyaniketan"),
    re.compile(r"(?i)department of"),
    re.compile(r"(?i)academic year"),
    re.compile(r"(?i)go,\s*change the world"),
    re.compile(r"(?i)bengaluru\s*-?\s*5?6?0?0?5?9"),
    re.compile(r"(?i)question paper"),
    re.compile(r"(?i)question paper and scheme"),
)

TABLE_NOISE_PATTERN = re.compile(
    r"(?i)^\s*(?:sl\.?\s*no|s\.?l\.?|no\.?|questions?|marks?|m|bt|co|bl|particulars|total|"
    r"course outcomes?|q\.?\s*no)\s*$"
)


@dataclass
class ExtractedQuestion:
    question_number: str
    extracted_text: str
    marks: Optional[int]
    original_page_number: int
    section: Optional[str] = None
    sequence: int = 0


@dataclass
class PageText:
    page_number: int
    text: str
    is_low_quality: bool = False
    ocr_used: bool = False


@dataclass
class PDFExtractionResult:
    pages: List[PageText]
    questions: List[ExtractedQuestion]
    total_pages: int
    low_confidence_extraction: bool = False
    ocr_used: bool = False
    notes: List[str] = field(default_factory=list)


def _normalize_ocr_line(line: str) -> str:
    line = line.replace("\u2013", "-").replace("\u2014", "-")
    line = re.sub(r"(\d)\s*\.{2,}\s*[:;]?\s*(\d)", r"\1.\2", line)
    line = re.sub(r"(\d)\s*\.{2,}\s*", r"\1. ", line)
    # Common OCR substitutions at the start of numbered questions: la. -> 1a.,
    # Sa. -> 5a., I. -> 1.
    line = re.sub(r"^[lI](?=[a-f][.)])", "1", line)
    line = re.sub(r"^[lI](?=[.)]\s)", "1", line)
    line = re.sub(r"^[sS](?=[a-f][.)])", "5", line)
    return line


def _is_instruction(rest: str) -> bool:
    lowered = rest.strip().lower()
    if not lowered:
        return False
    return any(lowered.startswith(prefix) for prefix in INSTRUCTION_PREFIXES)


def _match_question_start(line: str):
    """Return (question_number, remainder) for a printed question start."""
    raw = _normalize_ocr_line(line.strip())
    if not raw:
        return None

    match = HIERARCHICAL_PATTERN.match(raw)
    if match:
        major = int(match.group("major"))
        minor = int(match.group("minor"))
        rest = (match.group("rest") or "").strip()
        if 1 <= major <= 30 and 1 <= minor <= 30 and not _is_instruction(rest):
            return f"{major}.{minor}", rest

    match = LETTER_PATTERN.match(raw)
    if match:
        rest = (match.group("rest") or "").strip()
        if not _is_instruction(rest):
            return f"{int(match.group('major'))}.{match.group('sub').lower()}", rest

    match = LETTER_DOT_PATTERN.match(raw)
    if match:
        rest = (match.group("rest") or "").strip()
        if not _is_instruction(rest):
            return f"{int(match.group('major'))}.{match.group('sub').lower()}", rest

    match = SUB_ONLY_PATTERN.match(raw)
    if match:
        return f"{int(match.group('major'))}.{match.group('sub').lower()}", ""

    match = MAIN_PATTERN.match(raw)
    if match:
        rest = (match.group("rest") or "").strip()
        if not _is_instruction(rest):
            return str(int(match.group("major"))), rest

    match = BRACKET_MAIN_PATTERN.match(raw)
    if match:
        rest = (match.group("rest") or "").strip()
        if not _is_instruction(rest):
            return str(int(match.group("major"))), rest

    return None


def extract_marks_from_text(text: str) -> tuple[str, Optional[int]]:
    """Extract an inline marks value and return the cleaned text."""
    marks_val: Optional[int] = None
    matches = list(MARKS_PATTERN.finditer(text))
    if matches:
        last_match = matches[-1]
        for group in last_match.groups():
            if group is not None:
                try:
                    marks_val = int(group)
                    break
                except ValueError:
                    pass

    cleaned_text = MARKS_PATTERN.sub("", text).strip()
    return cleaned_text, marks_val


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if MARKS_LINE_PATTERN.match(stripped):
        return True
    if COURSE_OUTCOME_LINE_PATTERN.match(stripped):
        return True
    if TABLE_NOISE_PATTERN.match(stripped):
        return True
    if len(stripped) <= 90 and any(pattern.search(stripped) for pattern in PAGE_HEADER_PATTERNS):
        return True
    if re.fullmatch(r"[\W_]+", stripped):
        return True
    return False


def _clean_question_text(lines: List[str], inline_marks: Optional[int]) -> str:
    usable = [line.strip() for line in lines if line.strip() and not _is_noise_line(line)]
    if not usable:
        return ""
    text = " ".join(usable)

    # Solutions are often printed immediately after a question.  Keep the
    # question wording and discard the answer that follows an explicit marker.
    solution_marker = re.search(r"\b(?:soln|solution|answer|ans)\s*[:.]", text, re.IGNORECASE)
    if solution_marker and solution_marker.start() > 15:
        text = text[: solution_marker.start()]

    text, _ = extract_marks_from_text(text)
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    # Strip trailing course-outcome / Bloom-level columns that are printed next
    # to the question text in many RVCE papers.
    for _ in range(3):
        stripped = re.sub(
            r"\s+(?:CO\s?[l1-9]\d?|L[1-6]|BT\s?\d)\s*$", "", text, flags=re.IGNORECASE
        ).strip(" .;:-")
        if stripped == text:
            break
        text = stripped
    if len(text) > 700:
        text = text[:700].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return text


def _is_valid_question(question_number: str, text: str) -> bool:
    if not text or len(text) < 8:
        return False
    if not re.search(r"[A-Za-z]{2,}", text):
        return False
    if _is_instruction(text):
        return False
    if text.lower().startswith(("soln", "solution", "answer", "ans")):
        return False
    return True


def parse_page_questions(
    page_text: str, page_num: int, current_section: Optional[str]
) -> tuple[List[ExtractedQuestion], Optional[str]]:
    """Parse question blocks from one page of extracted PDF text."""
    questions: List[ExtractedQuestion] = []
    lines = page_text.splitlines()
    active_section = current_section

    current_number: Optional[str] = None
    current_lines: List[str] = []
    current_marks: Optional[int] = None
    pending_block_marks: Optional[int] = None

    def next_non_empty(index: int) -> str:
        for candidate in lines[index + 1 :]:
            if candidate.strip():
                return candidate.strip()
        return ""

    def flush_current() -> None:
        nonlocal current_number, current_lines, current_marks, pending_block_marks
        if not current_number:
            current_lines = []
            current_marks = None
            pending_block_marks = None
            return
        text = _clean_question_text(current_lines, current_marks)
        _, inline_marks = extract_marks_from_text(" ".join(current_lines))
        marks = current_marks if current_marks is not None else inline_marks
        if marks is None:
            marks = pending_block_marks
        if _is_valid_question(current_number, text):
            questions.append(
                ExtractedQuestion(
                    question_number=current_number,
                    extracted_text=text,
                    marks=marks,
                    original_page_number=page_num,
                    section=active_section,
                )
            )
        current_number = None
        current_lines = []
        current_marks = None
        pending_block_marks = None

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        if MODULE_PATTERN.match(line):
            flush_current()
            active_section = line
            continue

        # Marks are frequently printed as a standalone column (01, 02, 10).
        marks_line = MARKS_LINE_PATTERN.match(line)
        if marks_line and current_number:
            value = int(marks_line.group(1))
            following = next_non_empty(index)
            if value <= 20 and (
                line.startswith("0")
                or COURSE_OUTCOME_LINE_PATTERN.match(following)
                or following.lower().startswith(("l", "co", "bt"))
            ):
                pending_block_marks = value
                continue

        started = _match_question_start(line)
        if started:
            flush_current()
            current_number, remainder = started
            if remainder:
                current_lines.append(remainder)
            continue

        sub_match = SUBQUESTION_PATTERN.match(line)
        if sub_match and current_number:
            parent_number = current_number
            flush_current()
            letter = sub_match.group(1) or sub_match.group(2)
            remainder = sub_match.group(3).strip()
            parent_match = re.match(r"^(\d+)(?:\.[a-f])?$", parent_number, re.IGNORECASE)
            if parent_match:
                current_number = f"{parent_match.group(1)}.{letter.lower()}"
            else:
                current_number = f"{parent_number}.{letter.lower()}"
            if remainder:
                current_lines.append(remainder)
            continue

        if current_number:
            current_lines.append(line)

    flush_current()
    return questions, active_section


def _ocr_page(page) -> str:
    """Best-effort OCR. Returns an empty string when OCR is unavailable."""
    if shutil.which("tesseract") is None:
        return ""
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return ""
    try:
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        return pytesseract.image_to_string(image) or ""
    except Exception as exc:  # pragma: no cover - depends on local OCR install
        logger.warning("OCR failed for page %s: %s", getattr(page, "number", "?"), exc)
        return ""


def extract_questions_from_pdf(pdf_bytes: bytes) -> PDFExtractionResult:
    """Extract page texts and structured questions from PDF binary data."""
    if not pdf_bytes:
        return PDFExtractionResult(
            pages=[], questions=[], total_pages=0, low_confidence_extraction=True
        )

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    pages: List[PageText] = []
    all_questions: List[ExtractedQuestion] = []
    current_section: Optional[str] = None
    has_low_quality = False
    ocr_used = False

    for page_index in range(total_pages):
        page = doc[page_index]
        page_number = page_index + 1
        text = (page.get_text("text") or "").strip()
        page_ocr_used = False

        if len(text) < 40:
            ocr_text = _ocr_page(page)
            if ocr_text.strip():
                text = ocr_text.strip()
                page_ocr_used = True
                ocr_used = True

        is_low_quality = len(text) < 40
        if is_low_quality:
            has_low_quality = True
            logger.warning("Page %d has very little extractable text", page_number)

        pages.append(
            PageText(
                page_number=page_number,
                text=text,
                is_low_quality=is_low_quality,
                ocr_used=page_ocr_used,
            )
        )

        if text:
            page_questions, current_section = parse_page_questions(
                text, page_number, current_section
            )
            all_questions.extend(page_questions)

    doc.close()

    # Fallback: if no structured question was found, keep substantial paragraphs
    # as low-confidence candidates rather than silently returning nothing.
    if not all_questions and pages:
        for page in pages:
            if not page.text:
                continue
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
            for paragraph in paragraphs:
                cleaned, marks = extract_marks_from_text(paragraph)
                if len(cleaned) >= 30 and re.search(r"[A-Za-z]{3,}", cleaned):
                    all_questions.append(
                        ExtractedQuestion(
                            question_number=str(len(all_questions) + 1),
                            extracted_text=cleaned,
                            marks=marks,
                            original_page_number=page.page_number,
                            section=None,
                        )
                    )

    # Deduplicate repeated blocks inside the same PDF (combined papers and
    # duplicated scheme pages are common in these uploads).
    deduped: List[ExtractedQuestion] = []
    seen = set()
    for question in all_questions:
        key = (question.question_number.lower(), re.sub(r"\W+", " ", question.extracted_text.lower()).strip())
        if key in seen:
            continue
        seen.add(key)
        question.sequence = len(deduped) + 1
        deduped.append(question)

    notes: List[str] = []
    if ocr_used:
        notes.append("OCR fallback was used for one or more low-text pages.")
    if has_low_quality and not ocr_used:
        notes.append(
            "Some pages had no extractable text and OCR was unavailable; those pages were skipped."
        )
    if not deduped:
        notes.append("No examination questions could be extracted from this PDF.")

    return PDFExtractionResult(
        pages=pages,
        questions=deduped,
        total_pages=total_pages,
        low_confidence_extraction=has_low_quality or len(deduped) == 0,
        ocr_used=ocr_used,
        notes=notes,
    )
