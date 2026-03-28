"""
Document Type Detector — FIX 4
Determines RBI document type at ingestion time using priority cascade:
  1. Explicit user parameter (highest priority)
  2. Filename pattern matching
  3. First-page text heuristic
  4. LLM classification fallback (optional)
"""

import re
import os
from pathlib import Path
from typing import Optional
from core.logger import logger
from core.schemas import DocumentType


# ── Filename Pattern Rules ────────────────────────────────────────────────

_FILENAME_PATTERNS = [
    (r"master\s*direction", DocumentType.MASTER_DIRECTION),
    (r"master\s*circular",  DocumentType.MASTER_DIRECTION),
    (r"gazette",             DocumentType.GAZETTE),
    (r"amendment",           DocumentType.AMENDMENT),
    (r"notification",        DocumentType.NOTIFICATION),
    (r"circular",            DocumentType.CIRCULAR),
]

# First-page phrase patterns
_PAGE_PATTERNS = [
    (r"master\s+direction",  DocumentType.MASTER_DIRECTION),
    (r"master\s+circular",   DocumentType.MASTER_DIRECTION),
    (r"gazette\s+of\s+india", DocumentType.GAZETTE),
    (r"amendment\s+to",       DocumentType.AMENDMENT),
    (r"it\s+is\s+hereby\s+notified", DocumentType.NOTIFICATION),
    (r"ref\s*:\s*rbi",        DocumentType.CIRCULAR),
    (r"a\.p\.\s*\(dir",       DocumentType.CIRCULAR),
    (r"dnbs.*circular",       DocumentType.CIRCULAR),
    (r"dbr.*circular",        DocumentType.CIRCULAR),
]


# ── Date Extractor (from filename + first page) ───────────────────────────

def _extract_date_from_filename(filename: str) -> Optional[str]:
    """
    Try to extract a date from filename.
    Patterns: 2025, 2013-14, August 14 2025, 14.08.2025
    Returns ISO string 'YYYY-MM-DD' or None.
    """
    # Full date patterns
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", filename)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", filename)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    # Year only → use Jan 1
    m = re.search(r"\b(20\d{2})\b", filename)
    if m:
        return f"{m.group(1)}-01-01"

    # Financial year e.g. 2013-14 → use 2013-04-01
    m = re.search(r"\b(20\d{2})-(\d{2})\b", filename)
    if m:
        return f"{m.group(1)}-04-01"

    return None


def _extract_date_from_text(text: str) -> Optional[str]:
    """Extract date from first-page text."""
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09",
        "oct": "10", "nov": "11", "dec": "12",
    }

    # "14 August 2025" or "August 14, 2025"
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(months.keys()) + r")\s*,?\s*(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        mo = months[m.group(2).lower()]
        return f"{m.group(3)}-{mo}-{m.group(1).zfill(2)}"

    m = re.search(
        r"(" + "|".join(months.keys()) + r")\s+(\d{1,2})\s*,?\s*(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        mo = months[m.group(1).lower()]
        return f"{m.group(3)}-{mo}-{m.group(2).zfill(2)}"

    # "dated July 1, 2011"
    m = re.search(
        r"dated\s+(" + "|".join(months.keys()) + r")\s+(\d{1,2})\s*,?\s*(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        mo = months[m.group(1).lower()]
        return f"{m.group(3)}-{mo}-{m.group(2).zfill(2)}"

    return None


# ── Core Detection Function ───────────────────────────────────────────────

def detect_document_type(
    filename: str,
    first_page_text: str = "",
    explicit_type: Optional[str] = None,
) -> dict:
    """
    Detect the RBI document type and document date.

    Priority:
      1. explicit_type (from API request)
      2. filename patterns
      3. first-page text patterns
      4. default → circular (safest fallback)

    Returns:
        {
            "document_type": str (DocumentType value),
            "document_date": str | None,
            "detection_method": str,
        }
    """
    filename_lower = filename.lower()
    first_page_lower = first_page_text[:2000].lower()

    # 1. Explicit user override
    if explicit_type:
        normalized = explicit_type.strip().lower().replace(" ", "_").replace("-", "_")
        try:
            doc_type = DocumentType(normalized).value
        except ValueError:
            doc_type = DocumentType.CIRCULAR.value
        doc_date = (
            _extract_date_from_filename(filename)
            or _extract_date_from_text(first_page_text)
        )
        logger.info(f"[DocTypeDetector] '{filename}' → {doc_type} (explicit)")
        return {
            "document_type": doc_type,
            "document_date": doc_date,
            "detection_method": "explicit",
        }

    # 2. Filename patterns
    for pattern, doc_type in _FILENAME_PATTERNS:
        if re.search(pattern, filename_lower):
            doc_date = (
                _extract_date_from_filename(filename)
                or _extract_date_from_text(first_page_text)
            )
            logger.info(f"[DocTypeDetector] '{filename}' → {doc_type.value} (filename match)")
            return {
                "document_type": doc_type.value,
                "document_date": doc_date,
                "detection_method": "filename_pattern",
            }

    # 3. First-page text
    if first_page_text:
        for pattern, doc_type in _PAGE_PATTERNS:
            if re.search(pattern, first_page_lower):
                doc_date = _extract_date_from_text(first_page_text) or _extract_date_from_filename(filename)
                logger.info(f"[DocTypeDetector] '{filename}' → {doc_type.value} (first-page text)")
                return {
                    "document_type": doc_type.value,
                    "document_date": doc_date,
                    "detection_method": "first_page_text",
                }

    # 4. Default fallback
    doc_date = _extract_date_from_filename(filename) or _extract_date_from_text(first_page_text)
    logger.warning(f"[DocTypeDetector] '{filename}' → circular (default fallback)")
    return {
        "document_type": DocumentType.CIRCULAR.value,
        "document_date": doc_date,
        "detection_method": "default_fallback",
    }


def is_base_document(document_type: str) -> bool:
    """Returns True if this document is a master_direction (base reference)."""
    return document_type == DocumentType.MASTER_DIRECTION.value
