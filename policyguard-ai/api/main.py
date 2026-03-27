"""
FastAPI application with PDF ingestion pipeline and SSE progress streaming.
Implements all 8 layers:
1. PDF Classifier (digital/scanned/mixed)
2. Semantic Chunker (paragraph-aware)
3. Chunk Filter (forms/tables removal)
4. Adaptive Batcher (token-aware)
5. Async LLM Router (multi-provider failover)
6. Two-Pass Verifier (CRITICAL rule validation)
7. Cache + SSE (instant repeat responses + UI progress)
8. Dedup + Confidence (auto-approval)
"""

import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from core.config import settings
from core.logger import logger
from agents.pdf_classifier import classify_pdf, extract_text_by_type
from core.semantic_chunker import semantic_chunk_pages
from core.chunk_filter import filter_chunks
from core.adaptive_batcher import adaptive_batch_chunks
from agents.llm_router import LLMRouter
from core.two_pass_verifier import TwoPassVerifier
from core.cache import get_pdf_hash, get_cached_rules, cache_rules, progress_generator
from core.dedup_validator import deduplicate_rules, apply_confidence_validation, filter_valid_rules
from core.cache import get_session_queue


# ── Pydantic Models ────────────────────────────────────────────────────

class RuleOutput(BaseModel):
    """Extracted compliance rule."""
    id: str
    title: str
    description: str
    severity: str                          # CRITICAL, HIGH, MEDIUM, LOW
    source_clause: Optional[str] = None
    page_number: Optional[int] = None
    paragraph_number: Optional[str] = None
    rule_type: Optional[str] = None
    category: Optional[str] = None
    act_section: Optional[str] = None
    confidence_score: Optional[float] = None
    is_approved: Optional[bool] = False
    approval_status: Optional[str] = "pending_review"


class ExtractionResponse(BaseModel):
    """Response from PDF extraction."""
    session_id: str
    pdf_name: str
    total_rules: int
    rules: List[RuleOutput]
    from_cache: bool
    processing_time_seconds: Optional[float] = None


class ProgressEvent(BaseModel):
    """Progress update event."""
    stage: str
    completed: int
    total: int
    percent: int
    message: Optional[str] = None


# ── FastAPI App ────────────────────────────────────────────────────────

app = FastAPI(
    title="PolicyGuard AI - 8-Layer Pipeline",
    description="PDF ingestion with classifier, chunker, filter, batcher, LLM router, verifier, cache, and dedup",
    version="2.0.0"
)


# Global LLM router initialization
try:
    llm_router = LLMRouter()
    logger.info("[API] LLMRouter initialized successfully")
except Exception as e:
    logger.error(f"[API] Failed to initialize LLMRouter: {e}")
    llm_router = None


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    logger.info("[API] PolicyGuard AI Pipeline v2.0 started")
    logger.info(f"[API] Environment: {settings.app_env}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "router_ready": llm_router is not None,
        "app_env": settings.app_env,
    }


# ── Helpers ───────────────────────────────────────────────────────────────

# Fields kept in output — explainability fields like plain_english and
# violation_message_template are intentionally excluded here and will be
# handled separately later.
_RULE_OUTPUT_FIELDS = {
    "title", "description", "severity", "source_clause",
    "page_number", "paragraph_number", "rule_type", "category",
    "act_section", "confidence_score", "is_approved", "approval_status",
}

def _build_rule_output(raw: dict) -> RuleOutput:
    """Build a RuleOutput from a raw rule dict, safely ignoring unknown fields."""
    filtered = {k: v for k, v in raw.items() if k in _RULE_OUTPUT_FIELDS}
    filtered["id"] = str(uuid.uuid4())[:8]
    return RuleOutput(**filtered)


@app.post("/extract")
async def extract_pdf(file: UploadFile = File(...)) -> ExtractionResponse:
    """
    Main endpoint: Upload PDF and extract compliance rules.
    Uses all 8 layers with automatic caching and SSE progress.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Save uploaded file
    temp_path = Path(settings.policy_pdf_dir) / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Write file
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # Generate session
        session_id = str(uuid.uuid4())[:8]
        queue = get_session_queue(session_id)
        
        # Check cache
        pdf_hash = get_pdf_hash(str(temp_path))
        cached = get_cached_rules(pdf_hash)
        
        if cached:
            logger.info(f"[API] Cache hit for {file.filename} (session {session_id})")
            await queue.close()
            return ExtractionResponse(
                session_id=session_id,
                pdf_name=file.filename,
                total_rules=len(cached),
                rules=[_build_rule_output(r) for r in cached],
                from_cache=True,
            )
        
        # Process PDF through all 8 layers
        result = await process_pdf_pipeline(
            str(temp_path),
            session_id,
            queue,
        )
        
        # Cache results
        if result["rules"]:
            cache_rules(pdf_hash, [dict(r) for r in result["rules"]])
        
        await queue.close()
        
        return ExtractionResponse(
            session_id=session_id,
            pdf_name=file.filename,
            total_rules=len(result["rules"]),
            rules=[_build_rule_output(r) for r in result["rules"]],
            from_cache=False,
            processing_time_seconds=result.get("processing_time"),
        )
    
    finally:
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


@app.get("/progress/{session_id}")
async def progress_stream(session_id: str):
    """
    Server-Sent Events endpoint for real-time progress updates.
    Frontend listens on this endpoint during PDF processing.
    """
    return StreamingResponse(
        progress_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ── Internal Pipeline ────────────────────────────────────────────────────

async def process_pdf_pipeline(
    pdf_path: str,
    session_id: str,
    queue,
) -> dict:
    """
    Processes PDF through all 8 layers.
    Reports progress via async queue.
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"[Pipeline] Session {session_id} | Processing {Path(pdf_path).name}")
        
        # ── Layer 1: PDF Classifier ────────────────────────────────────────
        classification = classify_pdf(pdf_path)
        await queue.put({
            "stage": "classification",
            "pdf_type": classification["type"],
            "text_pages": classification["text_pages"],
            "image_pages": classification["image_pages"],
        })
        
        # ── Layer 1b: Extract text ─────────────────────────────────────────
        pages = extract_text_by_type(pdf_path, classification)
        await queue.put({
            "stage": "extraction",
            "pages_extracted": len(pages),
        })
        
        # ── Layer 2: Semantic Chunker ──────────────────────────────────────
        chunks = semantic_chunk_pages(pages)
        await queue.put({
            "stage": "chunking",
            "chunks_created": len(chunks),
        })
        
        # ── Layer 3: Chunk Filter ──────────────────────────────────────────
        filtered_chunks, skipped = filter_chunks(chunks)
        await queue.put({
            "stage": "filtering",
            "chunks_remaining": len(filtered_chunks),
            "chunks_skipped": skipped,
        })
        
        # ── Layer 4: Adaptive Batcher ──────────────────────────────────────
        batches = adaptive_batch_chunks(filtered_chunks, provider="together")
        await queue.put({
            "stage": "batching",
            "batches_created": len(batches),
        })
        
        # ── Layer 5: Async LLM Router ──────────────────────────────────────
        if not llm_router:
            raise RuntimeError("LLM Router not initialized")
        
        system_prompt = _build_system_prompt()
        
        async def progress_callback(event):
            await queue.put({
                "stage": "extraction",
                **event
            })
        
        router_result = await llm_router.extract_all_batches_async(
            batches,
            system_prompt,
            progress_callback,
        )
        extracted_rules = router_result.get("rules", [])
        
        await queue.put({
            "stage": "llm_complete",
            "rules_extracted": len(extracted_rules),
            "provider": router_result.get("provider"),
        })
        
        # ── Layer 6: Two-Pass Verifier ─────────────────────────────────────
        if settings.enable_verification and extracted_rules:
            verifier = TwoPassVerifier(pages)
            verified_rules = verifier.verify_critical_rules(extracted_rules)
            await queue.put({
                "stage": "verification",
                "rules_verified": len(verified_rules),
            })
        else:
            verified_rules = extracted_rules
        
        # ── Layer 8a: Deduplication ───────────────────────────────────────
        deduped_rules, removed = deduplicate_rules(verified_rules)
        await queue.put({
            "stage": "deduplication",
            "rules_final": len(deduped_rules),
            "duplicates_removed": len(removed),
        })
        
        # ── Layer 8b: Confidence Validation ────────────────────────────────
        valid_rules, invalid = filter_valid_rules(deduped_rules)
        auto_approved, flagged = apply_confidence_validation(valid_rules)
        
        await queue.put({
            "stage": "validation",
            "valid_rules": len(valid_rules),
            "invalid_rules": len(invalid),
            "auto_approved": len(auto_approved),
        })
        
        processing_time = time.time() - start_time
        
        return {
            "rules": auto_approved + flagged,
            "processing_time": processing_time,
            "statistics": {
                "total_pages": len(pages),
                "total_chunks": len(chunks),
                "filtered_chunks": len(filtered_chunks),
                "batches": len(batches),
                "extracted_rules": len(extracted_rules),
                "verified_rules": len(verified_rules),
                "final_rules": len(auto_approved + flagged),
                "auto_approved": len(auto_approved),
                "pending_review": len(flagged),
                "processing_seconds": round(processing_time, 2),
            }
        }
    
    except Exception as e:
        logger.error(f"[Pipeline] Session {session_id} failed: {e}", exc_info=True)
        await queue.put({
            "stage": "error",
            "error": str(e),
        })
        raise


def _build_system_prompt() -> str:
    """Build system prompt for LLM extraction."""
    return """You are an expert compliance rule extractor from policy documents.

Extract all compliance rules, obligations, and requirements from the provided policy text chunks.

For each rule, provide:
- title: Short rule title (5-15 words)
- description: Full rule description (20-500 words)
- severity: CRITICAL (must comply), HIGH (should comply), MEDIUM (recommended), or LOW (advisory)
- source_clause: The exact sentence from the text that supports this rule
- rule_type: validation, threshold, process, approval, documentation, etc.

Return only valid JSON with structure:
{
  "rules": [
    {
      "title": "...",
      "description": "...",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "source_clause": "...",
      "rule_type": "...",
      "page_number": NUMBER,
      "confidence_score": 0.0 to 1.0
    }
  ]
}

Be accurate. Only extract rules that are explicitly stated in the document.
Never hallucinate thresholds or requirements not in the text."""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
