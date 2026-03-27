"""
Layer 4: Token-Aware Adaptive Batcher
Instead of "5 chunks per call always", fills each call to 80% of LLM context limit.
Scales automatically from 1-page PDFs (1 call) to 300-page PDFs (30+ calls).
"""

from typing import List, Dict
from core.chunk_filter import should_skip_chunk
from core.logger import logger

# Conservative limits — 80% of actual to leave room for system prompt + output
PROVIDER_LIMITS = {
    "together":   6000,   # Llama 4 Scout context, smaller batches for stability
    "openrouter": 6000,   # varies by routed model
    "groq":       3000,   # 30K TPM limit means smaller batches to throttle less
}

SYSTEM_PROMPT_TOKENS = 900   # tokens reserved for system prompt
OUTPUT_TOKENS        = 2000  # tokens reserved for LLM response per batch
CHARS_PER_TOKEN      = 4     # approximate for English text


def adaptive_batch_chunks(chunks: List[Dict],
                          provider: str = "together") -> List[List[Dict]]:
    """
    Creates token-aware batches for LLM calls.
    Each batch uses up to 80% of the provider's safe context limit.
    
    Small PDFs may fit in 1-2 calls. Large PDFs scale automatically.

    Args:
        chunks:   list of chunk dicts from SemanticChunker
        provider: "together" | "openrouter" | "groq"

    Returns:
        list of batches, each batch is list of chunk dicts
    """
    max_tokens    = PROVIDER_LIMITS.get(provider, 4000)
    available     = max_tokens - SYSTEM_PROMPT_TOKENS - OUTPUT_TOKENS

    # Step 1: Filter non-policy chunks
    filtered = []
    skipped  = 0
    for chunk in chunks:
        text = chunk.get("text", "") or chunk.get("page_content", "")
        if should_skip_chunk(text):
            skipped += 1
        else:
            filtered.append(chunk)

    logger.info(f"[AdaptiveBatcher] Input: {len(chunks)} chunks | "
               f"After filter: {len(filtered)} chunks | "
               f"Provider: {provider} | "
               f"Available tokens: {available}")

    # Step 2: Pack chunks into token-aware batches
    batches       = []
    current_batch = []
    current_tokens = 0

    for chunk in filtered:
        text         = chunk.get("text", "")
        chunk_tokens = len(text) // CHARS_PER_TOKEN

        # If this single chunk is too large, truncate it
        if chunk_tokens > available:
            logger.warning(f"[AdaptiveBatcher] Chunk exceeds available tokens "
                          f"({chunk_tokens} > {available}). Truncating.")
            chunk["text"] = text[:available * CHARS_PER_TOKEN]
            chunk_tokens  = available

        # If adding chunk exceeds limit, save current batch and start new one
        if current_tokens + chunk_tokens > available and current_batch:
            batches.append(current_batch)
            logger.debug(f"[AdaptiveBatcher] Batch {len(batches)}: "
                        f"{len(current_batch)} chunks, {current_tokens} tokens")
            current_batch  = []
            current_tokens = 0

        current_batch.append(chunk)
        current_tokens += chunk_tokens

    # Save last batch
    if current_batch:
        batches.append(current_batch)
        logger.debug(f"[AdaptiveBatcher] Batch {len(batches)} (final): "
                    f"{len(current_batch)} chunks, {current_tokens} tokens")

    total_chunks = sum(len(b) for b in batches)
    avg_chunks = total_chunks // len(batches) if batches else 0
    
    logger.info(f"[AdaptiveBatcher] Final: {total_chunks} chunks → {len(batches)} batches | "
               f"Avg {avg_chunks} chunks/batch | "
               f"Skipped {skipped} non-policy chunks")
    
    return batches


def estimate_batch_cost(batches: List[List[Dict]], provider: str) -> Dict:
    """
    Estimate API cost and time for processing all batches.
    
    Args:
        batches: Output from adaptive_batch_chunks()
        provider: Provider name
        
    Returns:
        Dict with estimated_calls, estimated_time_seconds, etc.
    """
    num_batches = len(batches)
    
    # Rough estimates
    time_per_call = {
        "together": 3,      # seconds
        "openrouter": 5,
        "groq": 4,
    }
    
    parallel_limit = {
        "together": 8,
        "openrouter": 5,
        "groq": 2,
    }
    
    time_per_batch_round = time_per_call.get(provider, 4)
    parallel = parallel_limit.get(provider, 3)
    rounds = (num_batches + parallel - 1) // parallel  # ceiling division
    
    return {
        "num_batches": num_batches,
        "estimated_calls": num_batches,
        "parallel_limit": parallel,
        "estimated_rounds": rounds,
        "estimated_time_seconds": rounds * time_per_batch_round,
        "estimated_time_minutes": rounds * time_per_batch_round / 60,
    }


def get_batch_stats(batches: List[List[Dict]]) -> Dict:
    """Get statistics about batch distribution."""
    if not batches:
        return {
            "total_batches": 0,
            "total_chunks": 0,
            "avg_chunks_per_batch": 0,
            "min_chunks": 0,
            "max_chunks": 0,
        }
    
    chunk_counts = [len(b) for b in batches]
    total_chunks = sum(chunk_counts)
    
    return {
        "total_batches": len(batches),
        "total_chunks": total_chunks,
        "avg_chunks_per_batch": total_chunks // len(batches),
        "min_chunks": min(chunk_counts),
        "max_chunks": max(chunk_counts),
    }
