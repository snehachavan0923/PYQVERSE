"""PDF extraction service for PYQVERSE examination question papers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import pymupdf

logger = logging.getLogger(__name__)

# Patterns for exam sections and modules
MODULE_PATTERN = re.compile(
    r"(?i)\b(?:module|unit|part)\s*[-:]?\s*([0-9ivxlcdm]+|[a-e])\b"
)

# Question number patterns at the beginning of lines or blocks
# Examples: "1. a)", "Q1. a)", "Q1 (a)", "1 (a)", "1. ", "Q1.", "1a.", "(1) (a)"
QUESTION_START_PATTERN = re.compile(
    r"(?m)^\s*(?:Q\.?\s*([0-9]{1,2})|([0-9]{1,2})\.|\(([0-9]{1,2})\))\s*(?:\(?([a-f])\)|\.([a-f])|([a-f])\.)?",
    re.IGNORECASE,
)

# Sub-question standalone patterns: "a)", "(a)", "a.", "(i)", "i)"
SUBQUESTION_PATTERN = re.compile(
    r"^\s*(?:\(?([a-f])\)|\b([a-f])\.)\s+",
    re.IGNORECASE,
)

# Marks patterns: "[10 Marks]", "(8 marks)", "[10]", "(10M)", "10 Marks"
MARKS_PATTERN = re.compile(
    r"(?:\[\s*([0-9]{1,2})\s*(?:marks?|m)?\s*\]|\(\s*([0-9]{1,2})\s*(?:marks?|m)\s*\)|\b([0-9]{1,2})\s*(?:marks?|m)\b)",
    re.IGNORECASE,
)


@dataclass
class ExtractedQuestion:
    question_number: str
    extracted_text: str
    marks: Optional[int]
    original_page_number: int
    section: Optional[str] = None


@dataclass
class PageText:
    page_number: int
    text: str
    is_low_quality: bool = False


@dataclass
class PDFExtractionResult:
    pages: List[PageText]
    questions: List[ExtractedQuestion]
    total_pages: int
    low_confidence_extraction: bool = False


def extract_marks_from_text(text: str) -> tuple[str, Optional[int]]:
    """Extract marks from text and return cleaned text along with marks int."""
    marks_val: Optional[int] = None
    matches = list(MARKS_PATTERN.finditer(text))
    if matches:
        # Usually the last marks pattern in the question is the assigned marks
        last_match = matches[-1]
        for g in last_match.groups():
            if g is not None:
                try:
                    marks_val = int(g)
                    break
                except ValueError:
                    pass

    # Remove marks string from question text to keep text clean
    cleaned_text = MARKS_PATTERN.sub("", text).strip()
    return cleaned_text, marks_val


def parse_page_questions(
    page_text: str, page_num: int, current_section: Optional[str]
) -> tuple[List[ExtractedQuestion], Optional[str]]:
    """Parse question blocks from a single page's text."""
    questions: List[ExtractedQuestion] = []
    lines = page_text.splitlines()

    current_main_q: Optional[str] = None
    current_sub_q: Optional[str] = None
    current_q_text_lines: List[str] = []
    active_section = current_section

    def flush_current():
        nonlocal current_main_q, current_sub_q, current_q_text_lines
        if not current_main_q and not current_sub_q:
            return
        raw_text = " ".join(" ".join(current_q_text_lines).split())
        if not raw_text:
            return

        cleaned_text, marks = extract_marks_from_text(raw_text)
        if not cleaned_text:
            cleaned_text = raw_text

        # Build composite question number
        if current_main_q and current_sub_q:
            q_num = f"{current_main_q}.{current_sub_q.lower()}"
        elif current_main_q:
            q_num = current_main_q
        else:
            q_num = current_sub_q or "1"

        questions.append(
            ExtractedQuestion(
                question_number=q_num,
                extracted_text=cleaned_text,
                marks=marks,
                original_page_number=page_num,
                section=active_section,
            )
        )
        current_q_text_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Check for section / module header
        mod_match = MODULE_PATTERN.search(line)
        if mod_match:
            flush_current()
            active_section = line
            continue

        # Check for main question or main + subquestion
        # Matches: "1. a)", "Q1. a)", "1 (a)", "1. ", "Q.2", etc.
        m = re.match(
            r"^(?:Q\.?\s*([0-9]{1,2})|([0-9]{1,2})\.|\(([0-9]{1,2})\))\s*(?:\(?([a-f])\)|\.([a-f])|([a-f])\.)?\s*(.*)$",
            line,
            re.IGNORECASE,
        )
        if m:
            flush_current()
            main_num = m.group(1) or m.group(2) or m.group(3)
            sub_letter = m.group(4) or m.group(5) or m.group(6)
            remainder = m.group(7) or ""

            current_main_q = main_num
            current_sub_q = sub_letter
            if remainder.strip():
                current_q_text_lines.append(remainder.strip())
            continue

        # Check for standalone sub-question under existing main question: "a)", "(b)", "c."
        sub_m = SUBQUESTION_PATTERN.match(line)
        if sub_m and current_main_q:
            flush_current()
            current_sub_q = sub_m.group(1) or sub_m.group(2)
            remainder = line[sub_m.end():].strip()
            if remainder:
                current_q_text_lines.append(remainder)
            continue

        # Normal line of text for the active question
        if current_main_q or current_sub_q:
            current_q_text_lines.append(line)

    flush_current()
    return questions, active_section


def extract_questions_from_pdf(pdf_bytes: bytes) -> PDFExtractionResult:
    """Extract page texts and structured questions from PDF binary data."""
    if not pdf_bytes:
        return PDFExtractionResult(pages=[], questions=[], total_pages=0, low_confidence_extraction=True)

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    pages: List[PageText] = []
    all_questions: List[ExtractedQuestion] = []
    current_section: Optional[str] = None
    has_low_quality = False

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_num = page_idx + 1
        text = page.get_text("text") or ""
        text = text.strip()

        is_low_quality = len(text) < 40
        if is_low_quality:
            has_low_quality = True
            logger.warning("Page %d has very little extracted text (%d characters)", page_num, len(text))

        pages.append(PageText(page_number=page_num, text=text, is_low_quality=is_low_quality))

        if text:
            page_questions, current_section = parse_page_questions(text, page_num, current_section)
            all_questions.extend(page_questions)

    doc.close()

    # Fallback heuristic: If no structured questions were matched with strict regex,
    # split non-empty blocks that look like numbered questions or paragraphs.
    if not all_questions and pages:
        for p in pages:
            if not p.text:
                continue
            # Try splitting paragraphs
            paragraphs = [para.strip() for para in p.text.split("\n\n") if para.strip()]
            q_counter = 1
            for para in paragraphs:
                if len(para) > 15:
                    cleaned, marks = extract_marks_from_text(para)
                    all_questions.append(
                        ExtractedQuestion(
                            question_number=str(q_counter),
                            extracted_text=cleaned or para,
                            marks=marks,
                            original_page_number=p.page_number,
                            section=None,
                        )
                    )
                    q_counter += 1

    return PDFExtractionResult(
        pages=pages,
        questions=all_questions,
        total_pages=total_pages,
        low_confidence_extraction=has_low_quality or len(all_questions) == 0,
    )
