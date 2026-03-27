"""
Layer 1: PDF Classifier
Detects PDF type (digital/scanned/mixed) and routes to appropriate extractor.
Critical for handling both searchable and image-based PDFs.
"""

import fitz  # PyMuPDF
from enum import Enum
from pathlib import Path
from typing import List, Dict
from core.logger import logger


class PDFType(str, Enum):
    DIGITAL = "digital"   # text-based, PyMuPDF works perfectly
    SCANNED = "scanned"   # image-based, needs OCR
    MIXED   = "mixed"     # some text pages, some image pages


def classify_pdf(pdf_path: str) -> dict:
    """
    Detects PDF type before extraction so the right parser is used.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        {type, total_pages, text_pages, image_pages, confidence, text_ratio}
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages  = len(doc)
        text_pages   = 0
        image_pages  = 0

        for page in doc:
            text = page.get_text("text").strip()
            # A real text page has at least 100 meaningful characters
            if len(text) >= 100:
                text_pages += 1
            else:
                # Check if page has images — indicates scanned
                images = page.get_images()
                if images:
                    image_pages += 1
                # If no text and no images: blank page, skip

        doc.close()

        text_ratio = text_pages / total_pages if total_pages > 0 else 0

        if text_ratio >= 0.85:
            pdf_type = PDFType.DIGITAL
        elif text_ratio <= 0.15:
            pdf_type = PDFType.SCANNED
        else:
            pdf_type = PDFType.MIXED

        result = {
            "type":        pdf_type,
            "total_pages": total_pages,
            "text_pages":  text_pages,
            "image_pages": image_pages,
            "text_ratio":  round(text_ratio, 2),
        }
        logger.info(f"[PDFClassifier] {pdf_path.name}: {pdf_type} | "
                   f"{text_pages}/{total_pages} text pages | "
                   f"text_ratio={result['text_ratio']}")
        return result
    
    except Exception as e:
        logger.error(f"[PDFClassifier] Error classifying {pdf_path.name}: {e}")
        raise


def extract_text_by_type(pdf_path: str, classification: dict) -> List[Dict]:
    """
    Routes to correct extractor based on PDF type.
    
    Args:
        pdf_path: Path to PDF file
        classification: Output from classify_pdf()
        
    Returns:
        list of {page: int, text: str}
    """
    pdf_type = classification["type"]

    if pdf_type == PDFType.DIGITAL:
        return _extract_digital(pdf_path)

    elif pdf_type == PDFType.SCANNED:
        return _extract_ocr(pdf_path)

    else:  # MIXED
        return _extract_mixed(pdf_path)


def _extract_digital(pdf_path: str) -> List[Dict]:
    """Fast path: direct text extraction with PyMuPDF."""
    pdf_path = Path(pdf_path)
    doc   = fitz.open(pdf_path)
    pages = []
    
    try:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if len(text) >= 80:
                pages.append({"page": i + 1, "text": text})
        
        logger.info(f"[PDFExtract] Digital: {len(pages)} pages with content from {pdf_path.name}")
        return pages
    finally:
        doc.close()


def _extract_ocr(pdf_path: str) -> List[Dict]:
    """
    OCR path for scanned PDFs.
    Uses pytesseract if available, otherwise warns user.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image

        images = convert_from_path(pdf_path, dpi=300)
        pages  = []
        
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(
                image,
                lang="eng",
                config="--psm 6",  # assume uniform block of text
            ).strip()
            if len(text) >= 80:
                pages.append({"page": i + 1, "text": text})

        logger.info(f"[PDFExtract] OCR: {len(pages)} pages extracted from {Path(pdf_path).name}")
        return pages

    except ImportError:
        logger.warning("[PDFExtract] pytesseract not installed. "
                      "Scanned pages will be skipped. "
                      "Install: pip install pytesseract pdf2image")
        return []
    except Exception as e:
        logger.error(f"[PDFExtract] OCR failed: {e}")
        return []


def _extract_mixed(pdf_path: str) -> List[Dict]:
    """
    Page-by-page: use direct text for text pages, OCR for image pages.
    """
    pdf_path = Path(pdf_path)
    doc   = fitz.open(pdf_path)
    pages = []

    try:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()

            if len(text) >= 100:
                # Text page — use direct extraction
                pages.append({"page": i + 1, "text": text})
            else:
                # Image page — use OCR on this page only
                try:
                    import pytesseract
                    from pdf2image import convert_from_path

                    page_images = convert_from_path(
                        str(pdf_path), dpi=300,
                        first_page=i + 1, last_page=i + 1
                    )
                    if page_images:
                        ocr_text = pytesseract.image_to_string(
                            page_images[0], lang="eng"
                        ).strip()
                        if len(ocr_text) >= 80:
                            pages.append({"page": i + 1, "text": ocr_text})
                except Exception as e:
                    logger.warning(f"[PDFExtract] OCR failed page {i+1} of {pdf_path.name}: {e}")

        logger.info(f"[PDFExtract] Mixed: {len(pages)} pages extracted from {pdf_path.name}")
        return pages
    finally:
        doc.close()
