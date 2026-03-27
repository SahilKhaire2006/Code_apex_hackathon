"""
Layer 2: Semantic Paragraph Chunker
Replaces RecursiveCharacterTextSplitter. Splits at paragraph boundaries.
Ensures obligations are never cut in half.
"""

import re
from typing import List, Dict
from core.logger import logger

# Patterns that indicate a new section or paragraph in legal documents
SECTION_PATTERNS = [
    r"^\d+\.\s+[A-Z]",          # "18. NBFCs should..."
    r"^Para\s+\d+",              # "Para 21"
    r"^\([a-z]\)\s+",            # "(a) The NBFC..."
    r"^\([ivxlcdm]+\)\s+",       # "(iii) All cash..."
    r"^[A-Z][a-z]+\s+\d+\.",    # "Section 12."
    r"^Annex-[IVX]+",            # "Annex-VI"
    r"^[A-Z]{2,}\s*:",           # "NOTE:", "IMPORTANT:"
    r"^\d+\.\d+\s+",             # "3.1 NBFCs..."
    r"^Chapter\s+\d+",           # "Chapter 3"
]

COMPILED_PATTERNS = [re.compile(p, re.MULTILINE) for p in SECTION_PATTERNS]

MAX_TOKENS_PER_CHUNK = 800    # ~3200 chars, safe for any LLM
MIN_CHARS_PER_CHUNK  = 80     # skip tiny fragments
CHARS_PER_TOKEN      = 4      # approximate for English text


def semantic_chunk_pages(pages: List[Dict]) -> List[Dict]:
    """
    Chunks pages into semantically complete paragraphs.
    Each chunk ends at a paragraph boundary, never mid-sentence.

    Args:
        pages: List of {page: int, text: str} from PDF extractor

    Returns:
        List of {text: str, page: int, chunk_index: int,
                 paragraph_number: str, char_count: int, metadata: dict}
    """
    all_chunks   = []
    chunk_index  = 0

    for page_data in pages:
        page_num  = page_data["page"]
        page_text = page_data["text"]

        # Split page text into paragraphs
        paragraphs = _split_into_paragraphs(page_text)

        # Group paragraphs into token-safe chunks
        current_chunk_paras = []
        current_char_count  = 0
        current_para_num    = ""

        for para in paragraphs:
            para_chars = len(para["text"])

            # If adding this paragraph would exceed limit, save current chunk
            if (current_char_count + para_chars > MAX_TOKENS_PER_CHUNK * CHARS_PER_TOKEN
                    and current_chunk_paras):
                chunk_text = "\n\n".join(p["text"] for p in current_chunk_paras)
                if len(chunk_text.strip()) >= MIN_CHARS_PER_CHUNK:
                    all_chunks.append({
                        "text":             chunk_text.strip(),
                        "page":             page_num,
                        "chunk_index":      chunk_index,
                        "paragraph_number": current_para_num,
                        "char_count":       len(chunk_text),
                        "metadata": {
                            "page":          page_num,
                            "chunk_index":   chunk_index,
                            "source":        f"page_{page_num}_chunk_{chunk_index}",
                        }
                    })
                    chunk_index += 1

                current_chunk_paras = []
                current_char_count  = 0

            current_chunk_paras.append(para)
            current_char_count += para_chars
            if para.get("section_marker"):
                current_para_num = para["section_marker"]

        # Save remaining paragraphs as final chunk for this page
        if current_chunk_paras:
            chunk_text = "\n\n".join(p["text"] for p in current_chunk_paras)
            if len(chunk_text.strip()) >= MIN_CHARS_PER_CHUNK:
                all_chunks.append({
                    "text":             chunk_text.strip(),
                    "page":             page_num,
                    "chunk_index":      chunk_index,
                    "paragraph_number": current_para_num,
                    "char_count":       len(chunk_text),
                    "metadata": {
                        "page":         page_num,
                        "chunk_index":  chunk_index,
                        "source":       f"page_{page_num}_chunk_{chunk_index}",
                    }
                })
                chunk_index += 1

    logger.info(f"[SemanticChunker] {len(pages)} pages → {len(all_chunks)} chunks "
               f"(avg {len(all_chunks)//max(len(pages),1) if pages else 0} chunks/page)")
    return all_chunks


def _split_into_paragraphs(text: str) -> List[Dict]:
    """Split page text into individual paragraphs with section markers."""
    # Split on double newlines first (most reliable paragraph separator)
    raw_paragraphs = re.split(r"\n\s*\n", text)
    paragraphs     = []

    for para_text in raw_paragraphs:
        para_text = para_text.strip()
        if not para_text:
            continue

        # Detect if this paragraph starts a new numbered section
        section_marker = ""
        for pattern in COMPILED_PATTERNS:
            match = pattern.match(para_text)
            if match:
                section_marker = match.group(0).strip()
                break

        paragraphs.append({
            "text":           para_text,
            "section_marker": section_marker,
        })

    return paragraphs


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (~4 chars per token for English)."""
    return len(text) // CHARS_PER_TOKEN


def get_chunk_stats(chunks: List[Dict]) -> Dict:
    """Return statistics about chunk distribution."""
    if not chunks:
        return {"total": 0, "avg_chars": 0, "min_chars": 0, "max_chars": 0}
    
    char_counts = [c["char_count"] for c in chunks]
    return {
        "total": len(chunks),
        "avg_chars": sum(char_counts) // len(chunks),
        "min_chars": min(char_counts),
        "max_chars": max(char_counts),
    }
