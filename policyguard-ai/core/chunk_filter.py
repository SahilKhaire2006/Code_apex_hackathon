"""
Layer 3: Chunk Filter
Drops forms, tables, appendices, and non-policy content before LLM call.
Saves ~30% of API calls by filtering early.
"""

import re
from typing import List, Dict
from core.logger import logger


# Patterns that indicate form/table/appendix content to skip
SKIP_PATTERNS = [
    r"^(Schedule|Annexure|Annex|Appendix|Form|Attachment)\s*[-:]",
    r"^(TABLE|Table)\s+OF\s+(CONTENTS|Contents)",
    r"^\s*\|.*\|.*\|",  # Table rows with pipes
    r"^(Name|Address|Date|Signature)(\s*[:=]|\s*\(\s*\))",  # Form fields
    r"^(Print|Sign|DateField|Checkbox|Radio\s+Button)",
    r"^(Page\s+\d+|Index|Bibliography|References|Glossary)",
    r"[✓✗☐☑]",  # Checkbox symbols
    r"^_{2,}",  # Signature lines
]

COMPILED_SKIP_PATTERNS = [re.compile(p, re.MULTILINE | re.IGNORECASE) 
                          for p in SKIP_PATTERNS]

# Minimum meaningful content for a chunk
MIN_POLICY_CHARS = 100


def should_skip_chunk(text: str) -> bool:
    """
    Checks if a chunk matches form/table/appendix patterns.
    
    Args:
        text: Chunk text to evaluate
        
    Returns:
        True if chunk should be skipped, False if it should be kept
    """
    if not text or len(text.strip()) < MIN_POLICY_CHARS:
        return True
    
    # Check for skip patterns
    for pattern in COMPILED_SKIP_PATTERNS:
        if pattern.search(text):
            return True
    
    # Check if chunk is mostly numbers/symbols (likely a table)
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count / len(text) < 0.4:  # Less than 40% alphabetic
        return True
    
    return False


def filter_chunks(chunks: List[Dict]) -> tuple[List[Dict], int]:
    """
    Filters out non-policy chunks.
    
    Args:
        chunks: List of chunks from SemanticChunker
        
    Returns:
        (filtered_chunks, num_skipped)
    """
    filtered = []
    skipped  = 0
    
    for chunk in chunks:
        text = chunk.get("text", "")
        if not should_skip_chunk(text):
            filtered.append(chunk)
        else:
            skipped += 1
            logger.debug(f"[ChunkFilter] Skipped chunk at page {chunk.get('page')}, "
                        f"index {chunk.get('chunk_index')}")
    
    logger.info(f"[ChunkFilter] {len(chunks)} chunks → {len(filtered)} kept "
               f"({skipped} skipped as non-policy = {(skipped/len(chunks)*100):.0f}% reduction)")
    
    return filtered, skipped


def get_filter_stats(chunks: List[Dict], filtered: List[Dict]) -> Dict:
    """Return statistics about filtering."""
    skipped = len(chunks) - len(filtered)
    return {
        "total_input": len(chunks),
        "total_output": len(filtered),
        "skipped": skipped,
        "skip_ratio": round(skipped / len(chunks) * 100, 1) if chunks else 0,
    }
