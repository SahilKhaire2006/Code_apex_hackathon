import pymupdf
import pdfplumber
from pathlib import Path
from core.logger import logger
from core.schemas import PolicyChunk


class IngestionAgent:
    """
    Reads a PDF and extracts clean text per page with metadata.
    Uses PyMuPDF for speed + pdfplumber as fallback for complex layouts.
    """

    def __init__(self):
        logger.info("IngestionAgent initialized")

    def extract(self, pdf_path: str) -> dict:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Extracting text from: {path.name}")

        pages = self._extract_with_pymupdf(pdf_path)

        # Fallback: if any page is empty, retry with pdfplumber
        empty_pages = [p for p in pages if not p["text"].strip()]
        if empty_pages:
            logger.warning(f"{len(empty_pages)} empty pages detected — retrying with pdfplumber")
            fallback = self._extract_with_pdfplumber(pdf_path)
            for page in empty_pages:
                pnum = page["page_number"]
                page["text"] = fallback.get(pnum, "")

        logger.info(f"Extraction complete — {len(pages)} pages extracted from {path.name}")
        return {
            "filename": path.name,
            "total_pages": len(pages),
            "pages": pages
        }

    def _extract_with_pymupdf(self, pdf_path: str) -> list[dict]:
        pages = []
        doc = pymupdf.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            pages.append({
                "page_number": page_num + 1,
                "text": text,
                "char_count": len(text)
            })
        doc.close()
        return pages

    def _extract_with_pdfplumber(self, pdf_path: str) -> dict:
        page_texts = {}
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                page_texts[i + 1] = text.strip()
        return page_texts