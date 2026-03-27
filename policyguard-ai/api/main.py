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
import html
import io
import re
import textwrap
from pathlib import Path
from urllib.parse import urljoin
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from starlette.datastructures import UploadFile as StarletteUploadFile
import aiohttp
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

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
from transactions.pipeline import run_transaction_pipeline_async


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


class LinkExtractionRequest(BaseModel):
    """Request body for URL-based policy extraction."""
    url: str


class CircularExtractionRequest(BaseModel):
    """Request body for circular code-based policy extraction."""
    circular_code: str


# Frontend-compatible shapes
class RuleItem(BaseModel):
    """Rule in frontend RuleItem shape."""
    id: str
    field: str
    operator: str
    threshold: str
    severity: str
    page: Optional[int] = None


class ViolationItem(BaseModel):
    id: str
    transactionId: str
    amount: float
    rule: str
    severity: str
    page: Optional[int] = None
    status: str


class ExplanationItem(BaseModel):
    id: str
    transactionId: str
    ruleId: str
    clause: str
    explanation: str


class PipelineResults(BaseModel):
    rules: List[RuleItem]
    violations: List[ViolationItem]
    explanations: List[ExplanationItem]


# ── FastAPI App ────────────────────────────────────────────────────────

app = FastAPI(
    title="PolicyGuard AI - 8-Layer Pipeline",
    description="PDF ingestion with classifier, chunker, filter, batcher, LLM router, verifier, cache, and dedup",
    version="2.0.0"
)

# CORS — allow the Next.js dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global LLM router initialization
try:
    llm_router = LLMRouter()
    logger.info("[API] LLMRouter initialized successfully")
except Exception as e:
    logger.error(f"[API] Failed to initialize LLMRouter: {e}")
    llm_router = None

# Module-level store for last completed pipeline result (used by /violations & /report)
_latest_result: dict = {"rules": [], "violations": [], "explanations": [], "pdf_name": ""}


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


def _rule_output_to_rule_item(rule: RuleOutput) -> RuleItem:
    """Convert backend RuleOutput to frontend-compatible RuleItem."""
    return RuleItem(
        id=rule.id,
        field=rule.rule_type or rule.category or "compliance",
        operator="must comply",
        threshold=rule.source_clause or rule.description[:80] if rule.source_clause or rule.description else "",
        severity=rule.severity,
        page=rule.page_number,
    )


def _write_temp_pdf(content: bytes, hint_name: str) -> Path:
    """Persist bytes as a temporary PDF file for pipeline processing."""
    safe_hint = re.sub(r"[^a-zA-Z0-9_-]", "-", hint_name)[:40] or "policy"
    temp_path = Path(settings.policy_pdf_dir) / f"url-{safe_hint}-{uuid.uuid4().hex[:8]}.pdf"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(content)
    return temp_path


async def _fetch_url(url: str) -> tuple[bytes, str, str]:
    """Fetch URL and return raw bytes, content-type, and final redirected URL."""
    timeout = aiohttp.ClientTimeout(total=35)
    headers = {
        "User-Agent": "PolicyGuardAI/2.0 (+https://localhost)",
        "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as response:
            if response.status >= 400:
                raise HTTPException(status_code=400, detail=f"Unable to fetch URL (HTTP {response.status})")
            return (
                await response.read(),
                response.headers.get("Content-Type", "").lower(),
                str(response.url),
            )


def _extract_pdf_links_from_html(html_content: str, base_url: str) -> list[str]:
    """Extract candidate PDF links from HTML anchors."""
    links = re.findall(r'href=["\']([^"\']+)["\']', html_content, flags=re.IGNORECASE)
    pdf_links: list[str] = []
    seen: set[str] = set()

    for raw_link in links:
        candidate = urljoin(base_url, raw_link.strip())
        if ".pdf" not in candidate.lower():
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        pdf_links.append(candidate)

    return pdf_links


def _html_to_plain_text(html_content: str) -> str:
    """Convert HTML content to readable plain text."""
    no_scripts = re.sub(r"<script[\s\S]*?</script>", " ", html_content, flags=re.IGNORECASE)
    no_styles = re.sub(r"<style[\s\S]*?</style>", " ", no_scripts, flags=re.IGNORECASE)
    with_breaks = re.sub(r"</(p|div|li|h1|h2|h3|h4|h5|h6|tr|br)>", "\\n", no_styles, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", with_breaks)
    unescaped = html.unescape(without_tags)
    lines = [re.sub(r"\s+", " ", line).strip() for line in unescaped.splitlines()]
    cleaned = [line for line in lines if len(line) > 2]
    return "\n".join(cleaned)


def _text_to_pdf_bytes(text_content: str, source_url: str) -> bytes:
    """Render plain text into a simple PDF for reuse by the existing pipeline."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    page_width, page_height = letter
    x_margin = 50
    y = page_height - 50

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(x_margin, y, "Policy Source (URL ingestion)")
    y -= 18
    pdf.setFont("Helvetica", 9)

    for line in textwrap.wrap(f"Source URL: {source_url}", width=95):
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 9)
            y = page_height - 50
        pdf.drawString(x_margin, y, line)
        y -= 13

    y -= 8
    for paragraph in text_content.splitlines():
        for line in textwrap.wrap(paragraph, width=100):
            if y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = page_height - 50
            pdf.drawString(x_margin, y, line)
            y -= 13
        y -= 6

    pdf.save()
    return buffer.getvalue()


async def _search_serper_candidates(seed_url: str) -> list[str]:
    """Use Serper to locate direct circular/master-direction resources, preferably PDFs."""
    api_key = settings.serper_api_key.strip()
    if not api_key:
        return []

    payload = {
        "q": f"{seed_url} RBI circular master direction pdf full text",
        "num": 8,
    }
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.post("https://google.serper.dev/search", json=payload) as response:
            if response.status >= 400:
                logger.warning(f"[API] Serper lookup failed with HTTP {response.status}")
                return []

            body = await response.json()
            organic = body.get("organic", [])

            links: list[str] = []
            seen: set[str] = set()
            for item in organic:
                link = str(item.get("link", "")).strip()
                if not link or link in seen:
                    continue
                seen.add(link)
                links.append(link)
            return links


async def _search_circular_code(circular_code: str) -> str:
    """Search for an RBI circular by code and return the best matching URL."""
    api_key = settings.serper_api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Serper API key not configured. Please provide SERPER_API_KEY in .env",
        )

    payload = {
        "q": f"RBI {circular_code} circular master direction pdf",
        "num": 10,
    }
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.post("https://google.serper.dev/search", json=payload) as response:
            if response.status >= 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"Serper search failed (HTTP {response.status})",
                )

            body = await response.json()
            organic = body.get("organic", [])

            if not organic:
                raise HTTPException(
                    status_code=404,
                    detail=f"No results found for circular code: {circular_code}",
                )

            best_link = None
            for item in organic:
                link = str(item.get("link", "")).strip()
                if not link:
                    continue
                if ".pdf" in link.lower():
                    best_link = link
                    break
                if best_link is None:
                    best_link = link

            if not best_link:
                raise HTTPException(
                    status_code=404,
                    detail=f"Could not find a valid URL for circular code: {circular_code}",
                )

            logger.info(f"[API] Circular code '{circular_code}' resolved to {best_link}")
            return best_link


async def _prepare_policy_pdf_from_url(url: str) -> tuple[Path, str]:
    """Resolve URL into a local PDF (direct PDF download, linked PDF, or HTML->PDF fallback)."""
    content, content_type, final_url = await _fetch_url(url)
    base_name = Path(final_url).name or "policy-from-link.pdf"

    if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
        return _write_temp_pdf(content, base_name), base_name

    page_html = content.decode("utf-8", errors="ignore")
    best_text = _html_to_plain_text(page_html)
    best_source = final_url

    direct_pdf_links = _extract_pdf_links_from_html(page_html, final_url)
    serper_links = await _search_serper_candidates(url)

    candidate_links: list[str] = []
    seen_candidates: set[str] = set()
    for candidate in [*direct_pdf_links, *serper_links]:
        if candidate in seen_candidates:
            continue
        seen_candidates.add(candidate)
        candidate_links.append(candidate)

    for candidate in candidate_links[:12]:
        try:
            candidate_content, candidate_type, candidate_final = await _fetch_url(candidate)
        except Exception:
            continue

        if "application/pdf" in candidate_type or candidate_final.lower().endswith(".pdf"):
            candidate_name = Path(candidate_final).name or "policy-from-link.pdf"
            return _write_temp_pdf(candidate_content, candidate_name), candidate_name

        candidate_html = candidate_content.decode("utf-8", errors="ignore")
        candidate_text = _html_to_plain_text(candidate_html)
        if len(candidate_text) > len(best_text):
            best_text = candidate_text
            best_source = candidate_final

    if len(best_text) < 500:
        raise HTTPException(
            status_code=400,
            detail="Unable to retrieve enough policy text from the provided link. Please upload PDF directly.",
        )

    rendered_pdf = _text_to_pdf_bytes(best_text, best_source)
    return _write_temp_pdf(rendered_pdf, "policy-from-link"), "policy-from-link.pdf"


# ── Main Extract Endpoint ─────────────────────────────────────────────────

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
            rules = [_build_rule_output(r) for r in cached]
            # Update latest result store
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = file.filename
            return ExtractionResponse(
                session_id=session_id,
                pdf_name=file.filename,
                total_rules=len(cached),
                rules=rules,
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

        rules = [_build_rule_output(r) for r in result["rules"]]

        # Update latest result store for /violations and /report
        _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
        _latest_result["pdf_name"] = file.filename
        
        return ExtractionResponse(
            session_id=session_id,
            pdf_name=file.filename,
            total_rules=len(result["rules"]),
            rules=rules,
            from_cache=False,
            processing_time_seconds=result.get("processing_time"),
        )
    
    finally:
        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


@app.post("/extract-from-link")
async def extract_from_link(payload: LinkExtractionRequest) -> ExtractionResponse:
    """
    Fetch a policy circular/master direction from URL and run the same 8-layer extraction pipeline.
    Supports direct PDF URLs, HTML pages with PDF links, and HTML text fallback.
    """
    normalized_url = payload.url.strip()
    if not re.match(r"^https?://", normalized_url, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Provide a valid http/https URL")

    temp_path: Optional[Path] = None
    source_name = "policy-from-link.pdf"

    try:
        temp_path, source_name = await _prepare_policy_pdf_from_url(normalized_url)

        session_id = str(uuid.uuid4())[:8]
        queue = get_session_queue(session_id)

        pdf_hash = get_pdf_hash(str(temp_path))
        cached = get_cached_rules(pdf_hash)

        if cached:
            logger.info(f"[API] Cache hit for URL policy source (session {session_id})")
            await queue.close()
            rules = [_build_rule_output(r) for r in cached]
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = source_name
            return ExtractionResponse(
                session_id=session_id,
                pdf_name=source_name,
                total_rules=len(cached),
                rules=rules,
                from_cache=True,
            )

        result = await process_pdf_pipeline(str(temp_path), session_id, queue)

        if result["rules"]:
            cache_rules(pdf_hash, [dict(r) for r in result["rules"]])

        await queue.close()

        rules = [_build_rule_output(r) for r in result["rules"]]
        _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
        _latest_result["pdf_name"] = source_name

        return ExtractionResponse(
            session_id=session_id,
            pdf_name=source_name,
            total_rules=len(result["rules"]),
            rules=rules,
            from_cache=False,
            processing_time_seconds=result.get("processing_time"),
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


@app.post("/extract-from-circular")
async def extract_from_circular(payload: CircularExtractionRequest) -> ExtractionResponse:
    """
    Search for an RBI circular by code using Serper, then extract rules from the discovered URL.
    This bridges the gap between user-friendly circular codes and the 8-layer extraction pipeline.
    """
    circular_code = payload.circular_code.strip()
    if not circular_code:
        raise HTTPException(status_code=400, detail="Provide a valid circular code")

    temp_path: Optional[Path] = None
    source_name = f"circular-{circular_code}.pdf"

    try:
        # Search for the circular using Serper
        resolved_url = await _search_circular_code(circular_code)
        logger.info(f"[API] Fetching circular '{circular_code}' from {resolved_url}")

        # Fetch and prepare the PDF (same logic as link-based ingestion)
        temp_path, source_name = await _prepare_policy_pdf_from_url(resolved_url)

        session_id = str(uuid.uuid4())[:8]
        queue = get_session_queue(session_id)

        pdf_hash = get_pdf_hash(str(temp_path))
        cached = get_cached_rules(pdf_hash)

        if cached:
            logger.info(f"[API] Cache hit for circular '{circular_code}' (session {session_id})")
            await queue.close()
            rules = [_build_rule_output(r) for r in cached]
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = source_name
            return ExtractionResponse(
                session_id=session_id,
                pdf_name=source_name,
                total_rules=len(cached),
                rules=rules,
                from_cache=True,
            )

        result = await process_pdf_pipeline(str(temp_path), session_id, queue)

        if result["rules"]:
            cache_rules(pdf_hash, [dict(r) for r in result["rules"]])

        await queue.close()

        rules = [_build_rule_output(r) for r in result["rules"]]
        _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
        _latest_result["pdf_name"] = source_name

        return ExtractionResponse(
            session_id=session_id,
            pdf_name=source_name,
            total_rules=len(result["rules"]),
            rules=rules,
            from_cache=False,
            processing_time_seconds=result.get("processing_time"),
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


# ── /extract-rules alias (frontend Phase 1 compatibility) ─────────────────

@app.post("/extract-rules")
async def extract_rules_alias(policy: UploadFile = File(...)):
    """
    Alias accepted by the frontend's extractRules() call.
    Delegates to the same 8-layer pipeline and returns
    a frontend-compatible {status, rules} response.
    """
    if not policy.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_path = Path(settings.policy_pdf_dir) / policy.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = await policy.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        session_id = str(uuid.uuid4())[:8]
        queue = get_session_queue(session_id)

        pdf_hash = get_pdf_hash(str(temp_path))
        cached = get_cached_rules(pdf_hash)

        if cached:
            await queue.close()
            rules = [_build_rule_output(r) for r in cached]
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = policy.filename
            return {"status": "complete", "session_id": session_id, "rules": [r.dict() for r in rules]}

        result = await process_pdf_pipeline(str(temp_path), session_id, queue)
        await queue.close()

        rules = [_build_rule_output(r) for r in result["rules"]]
        _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
        _latest_result["pdf_name"] = policy.filename

        return {
            "status": "complete",
            "session_id": session_id,
            "rules": [r.dict() for r in rules],
        }
    finally:
        if temp_path.exists():
            temp_path.unlink()


# ── /ingest alias (frontend Phase 1 compatibility) ────────────────────────

@app.post("/ingest")
async def ingest_policy(policy: UploadFile = File(...)):
    """
    Stub accepted by the frontend's ingestPolicy() call.
    Lightweight — just validates the PDF and returns quickly so
    the UI progress animation can proceed while the real heavy
    extraction happens in /extract-rules.
    """
    if not policy.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    # Read and discard — real processing is in /extract-rules
    await policy.read()
    return {"status": "complete", "message": f"Policy '{policy.filename}' ingested"}


# ── /validate — real 3-stage transaction pipeline ─────────────────────────

_latest_txn_result: dict = {}  # stores last transaction run for /violations

@app.post("/validate")
async def validate_transactions(request: Request):
    """
    Receives a CSV/XLS/XLSX file, runs the full 3-stage transaction pipeline
    (Parse → Preprocess → Store) from the codeapex module, and returns
    structured results. Violations are stored in memory for /violations.
    """
    global _latest_txn_result

    try:
        # Raise part size so large transaction files can be uploaded via multipart/form-data.
        form = await request.form(max_part_size=1024 * 1024 * 1024)  # 1 GB
    except Exception as e:
        logger.error(f"[API] Multipart parse failed in /validate: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid upload payload")

    upload = form.get("file") or form.get("transactions")
    if not isinstance(upload, StarletteUploadFile):
        raise HTTPException(
            status_code=400,
            detail="Missing file upload. Use form-data field 'file'.",
        )

    # Save uploaded file to data/transactions/
    txn_dir = Path(settings.transaction_csv_dir)
    txn_dir.mkdir(parents=True, exist_ok=True)
    dest = txn_dir / (upload.filename or "upload.csv")

    logger.info(f"[API] Received validation request for {upload.filename} ({upload.content_type})")

    try:
        content = await upload.read()
        dest.write_bytes(content)

        logger.info(f"[API] Running transaction pipeline on {upload.filename} ({len(content):,} bytes)")

        # Run the pipeline in a thread pool (blocking I/O)
        result = await run_transaction_pipeline_async(str(dest))

        _latest_txn_result = result
        logger.info(
            f"[API] Transaction pipeline {result['status']} — "
            f"{result['rows_stored']} rows stored, "
            f"{result['violations_count']} violations"
        )

        return result
    except Exception as e:
        logger.error(f"[API] Error in /validate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ── /violations ───────────────────────────────────────────────────────────

@app.get("/violations")
async def get_violations() -> PipelineResults:
    """
    Returns:
    - Rules from the most recent /extract run
    - Violations from the most recent /validate (transaction pipeline) run
    """
    rules = [RuleItem(**r) for r in _latest_result.get("rules", [])]

    # Build ViolationItem list from transaction pipeline results
    raw_violations = _latest_txn_result.get("violations", [])
    violations = []
    for i, v in enumerate(raw_violations):
        violations.append(ViolationItem(
            id=f"VIO-{i+1:03d}",
            transactionId=f"TXN-{i+1:04d}",
            amount=0.0,
            rule=v.get("rule", "Unknown Rule"),
            severity=v.get("severity", "MEDIUM"),
            page=None,
            status=v.get("verdict", "VIOLATION"),
        ))


    return PipelineResults(
        rules=rules,
        violations=violations,
        explanations=[],
    )


# ── /report ───────────────────────────────────────────────────────────────

@app.get("/report")
async def download_report():
    """
    Returns a plain-text compliance report for the last extracted PDF.
    Frontend downloads this as a blob via downloadReportBlob().
    """
    pdf_name = _latest_result.get("pdf_name", "unknown")
    rules = _latest_result.get("rules", [])

    lines = [
        "POLICYGUARD AI — COMPLIANCE EXTRACTION REPORT",
        "=" * 50,
        f"Document: {pdf_name}",
        f"Rules Extracted: {len(rules)}",
        "",
        "EXTRACTED RULES",
        "-" * 50,
    ]
    for i, r in enumerate(rules, 1):
        lines.append(f"{i}. [{r.get('severity', 'N/A')}] {r.get('field', 'Rule')}")
        lines.append(f"   Clause: {r.get('threshold', '')[:120]}")
        lines.append("")

    report_text = "\n".join(lines)
    return PlainTextResponse(
        content=report_text,
        headers={"Content-Disposition": "attachment; filename=policyguard-compliance-report.txt"},
    )


# ── SSE Progress Stream ────────────────────────────────────────────────────

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
