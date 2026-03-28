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

Provenance & Shared Registry Features:
- Document type detection (master_direction vs circular)
- Shared Supabase cloud registry (cross-bank reuse)
- Rule status: NEW / EXISTING / MODIFIED / SUPERSEDED / CLARIFICATION
- Provenance chain tracking per rule
"""

import uuid
import asyncio
import html
import io
import re
import textwrap
from pathlib import Path
from urllib.parse import urljoin
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any
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
from core.document_type_detector import detect_document_type, is_base_document
from agents.delta_analyzer import RuleDeltaAnalyzer


# ── Pydantic Models ────────────────────────────────────────────────────

class RuleOutput(BaseModel):
    """Extracted compliance rule — with provenance fields."""
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
    # ── Provenance & Status (FIX 1 + FIX 2) ─────────────────────────────
    status: Optional[str] = "NEW"          # NEW | EXISTING | MODIFIED | SUPERSEDED | CLARIFICATION
    source_document_name: Optional[str] = None
    source_document_type: Optional[str] = None
    source_document_date: Optional[str] = None
    last_modified_by: Optional[str] = None
    modification_summary: Optional[str] = None
    provenance_chain: Optional[List[Any]] = []
    provenance_display: Optional[str] = None  # Human-readable provenance (FIX 7)


class ExtractionResponse(BaseModel):
    """Response from PDF extraction."""
    session_id: str
    pdf_name: str
    total_rules: int
    rules: List[RuleOutput]
    from_cache: bool
    processing_time_seconds: Optional[float] = None
    document_type: Optional[str] = None        # Detected document type
    from_shared_registry: Optional[bool] = False  # True if fetched from shared Supabase registry
    status_summary: Optional[dict] = None      # {NEW: N, EXISTING: M, MODIFIED: K, ...}


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
    rule_id: Optional[str] = None


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

# CORS — allow any origin for testing (including file:// protocol)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    # Provenance fields
    "status", "source_document_name", "source_document_type", "source_document_date",
    "last_modified_by", "modification_summary", "provenance_chain",
}


def _format_provenance_display(rule: dict) -> str:
    """
    FIX 7 — Build a human-readable provenance string for UI display.
    """
    status = rule.get("status", "NEW")
    src = rule.get("source_document_name", "unknown")
    mod = rule.get("last_modified_by")
    summary = rule.get("modification_summary")
    chain = rule.get("provenance_chain") or []

    # Find master direction in chain
    master = next(
        (e.get("document") for e in chain if e.get("type") == "master_direction"),
        None
    )

    if status == "EXISTING":
        base = master or src
        return (
            f"Originally introduced in: {base}\n"
            f"Referenced (unchanged) by: {src}"
        )
    elif status == "MODIFIED":
        base = master or src
        change = f"\nChange: {summary}" if summary else ""
        return (
            f"Originally introduced in: {base}\n"
            f"Modified by: {mod or src}"
            f"{change}"
        )
    elif status == "NEW" and src:
        return f"Introduced by: {src}\nNot present in Master Direction"
    elif status == "SUPERSEDED":
        base = master or src
        return (
            f"Originally introduced in: {base}\n"
            f"Superseded by: {mod or src}"
        )
    elif status == "CLARIFICATION":
        base = master or src
        return (
            f"Clarification of rule from: {base}\n"
            f"Clarified by: {src}"
        )
    return f"Introduced by: {src}"


def _build_rule_output(raw: dict) -> RuleOutput:
    """Build a RuleOutput from a raw rule dict, safely ignoring unknown fields."""
    filtered = {k: v for k, v in raw.items() if k in _RULE_OUTPUT_FIELDS}
    filtered["id"] = raw.get("rule_id") or str(uuid.uuid4())[:8]
    filtered["provenance_display"] = _format_provenance_display(raw)
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


# ── /extract-rules — Main extraction endpoint with provenance ────────────

@app.post("/extract-rules")
async def extract_rules_alias(
    policy: UploadFile = File(...),
    document_type: Optional[str] = Form(default=None),
):
    """
    Alias accepted by the frontend's extractRules() call.
    Delegates to the same 8-layer pipeline and returns
    a frontend-compatible {status, rules} response.

    NEW FEATURES:
    - document_type: Optional form field (master_direction | circular | amendment | gazette).
      Auto-detected from filename + first page if not provided.
    - Shared registry: If the same PDF was already processed by any bank,
      returns existing rules from Supabase without re-processing.
    - Delta analysis: For circulars, compares rules against Master Direction
      to assign NEW / EXISTING / MODIFIED / SUPERSEDED / CLARIFICATION status.
    """
    if not policy.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    temp_path = Path(settings.policy_pdf_dir) / policy.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        content = await policy.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        filename = policy.filename
        session_id = str(uuid.uuid4())[:8]
        queue = get_session_queue(session_id)

        # ── SHARED REGISTRY CHECK — FIX Feature 1 ─────────────────────────
        # If another bank has already processed this exact file, return those rules
        shared_rules = []
        try:
            from core.supabase_client import fetch_rules_for_document, _supabase_available
            if _supabase_available():
                shared_rules = fetch_rules_for_document(filename)
        except Exception as _e:
            logger.warning(f"[API] Shared registry check failed: {_e}")

        if shared_rules:
            logger.info(
                f"[API] SHARED REGISTRY HIT: {len(shared_rules)} rules found for '{filename}' "
                f"— returning without re-processing"
            )
            await queue.close()
            rules = [_build_rule_output(r) for r in shared_rules]
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = filename
            status_summary = {}
            for r in shared_rules:
                s = r.get("status", "NEW")
                status_summary[s] = status_summary.get(s, 0) + 1
            return {
                "status": "complete",
                "session_id": session_id,
                "rules": [r.dict() for r in rules],
                "from_shared_registry": True,
                "document_type": shared_rules[0].get("source_document_type") if shared_rules else None,
                "status_summary": status_summary,
                "message": (
                    f"Rules for '{filename}' already exist in the shared registry "
                    f"({len(shared_rules)} rules). Returned without re-processing."
                ),
            }

        # ── PROCESSING ORDER CONSTRAINT CHECK ────────────────────────────────
        # Extract first page text for document type detection
        first_page_text = ""
        try:
            import fitz
            doc = fitz.open(str(temp_path))
            if len(doc) > 0:
                first_page_text = doc[0].get_text("text")[:2000]
            doc.close()
        except Exception:
            pass

        # Detect document type
        detection = detect_document_type(
            filename=filename,
            first_page_text=first_page_text,
            explicit_type=document_type,
        )
        detected_type = detection["document_type"]
        detected_date = detection.get("document_date")
        logger.info(
            f"[API] Document type for '{filename}': {detected_type} "
            f"(method={detection['detection_method']}, date={detected_date})"
        )

        # Enforce: circulars must have master_direction in registry first
        if not is_base_document(detected_type):
            try:
                from core.supabase_client import base_document_exists, _supabase_available
                if _supabase_available() and not base_document_exists():
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Processing order constraint: Please upload the Master Direction "
                            "base document before uploading circulars or amendments. "
                            "The delta analysis requires Master Direction rules to be "
                            "available in the shared registry."
                        ),
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # Supabase not configured — allow anyway

        # ── LOCAL CACHE CHECK ────────────────────────────────────────────────
        pdf_hash = get_pdf_hash(str(temp_path))
        cached = get_cached_rules(pdf_hash)

        if cached:
            await queue.close()
            rules = [_build_rule_output(r) for r in cached]
            _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
            _latest_result["pdf_name"] = filename
            
            # Rebuild status summary for cached rules
            status_summary = {}
            for r in cached:
                s = r.get("status", "NEW")
                status_summary[s] = status_summary.get(s, 0) + 1
                
            # Ensure the cached rules are still fully synced to both local and shared registries
            _sync_rules_to_shared_registry(cached, filename, detected_type, detected_date)
            _record_document_stats(filename, detected_type, detected_date, status_summary)
            
            return {
                "status": "complete",
                "session_id": session_id,
                "rules": [r.dict() for r in rules],
                "from_shared_registry": False,
                "document_type": detected_type,
                "status_summary": status_summary,
            }

        # ── FULL PIPELINE ────────────────────────────────────────────────────
        result = await process_pdf_pipeline(str(temp_path), session_id, queue)
        raw_rules = result["rules"]

        # ── DELTA ANALYSIS — FIX 3 (for non-master_direction docs) ──────────
        if raw_rules and not is_base_document(detected_type):
            logger.info(
                f"[API] Running delta analysis for {len(raw_rules)} rules "
                f"from '{filename}' (type={detected_type})"
            )
            try:
                analyzer = RuleDeltaAnalyzer(llm_router=llm_router)
                raw_rules = await analyzer.analyze_deltas(
                    new_rules=raw_rules,
                    tenant_id="global_rbi",
                    document_type=detected_type,
                    source_document_name=filename,
                    source_document_date=detected_date,
                    master_direction_name="Master Direction",
                )
            except Exception as e:
                logger.error(f"[API] Delta analysis failed: {e} — rules will be marked NEW")
                for r in raw_rules:
                    r.setdefault("status", "NEW")
                    r.setdefault("source_document_name", filename)
                    r.setdefault("source_document_type", detected_type)
        else:
            # Master direction: stamp provenance directly
            for r in raw_rules:
                r.setdefault("status", "NEW")
                r["source_document_name"] = filename
                r["source_document_type"] = detected_type
                r["source_document_date"] = detected_date
                r["provenance_chain"] = [{
                    "document": filename,
                    "type": detected_type,
                    "date": detected_date,
                    "action": "introduced",
                }]

        # ── SYNC TO SHARED SUPABASE REGISTRY ────────────────────────────────
        # Only insert NEW / MODIFIED / SUPERSEDED / CLARIFICATION rules into Supabase
        # (EXISTING rules already have their provenance updated inside delta_analyzer)
        _sync_rules_to_shared_registry(raw_rules, filename, detected_type, detected_date)

        # Cache results locally
        if raw_rules:
            cache_rules(pdf_hash, raw_rules)

        await queue.close()

        rules = [_build_rule_output(r) for r in raw_rules]
        _latest_result["rules"] = [_rule_output_to_rule_item(r).dict() for r in rules]
        _latest_result["pdf_name"] = filename

        # Build status summary
        status_summary = {}
        for r in raw_rules:
            s = r.get("status", "NEW")
            status_summary[s] = status_summary.get(s, 0) + 1

        # Record ingestion document
        _record_document_stats(filename, detected_type, detected_date, status_summary)

        return {
            "status": "complete",
            "session_id": session_id,
            "rules": [r.dict() for r in rules],
            "from_shared_registry": False,
            "document_type": detected_type,
            "status_summary": status_summary,
        }
    finally:
        if temp_path.exists():
            temp_path.unlink()


# ── /rules/by-document — Query rules by source document ──────────────────

@app.get("/rules/by-document")
async def rules_by_document(document_name: str):
    """
    Return all rules extracted from a specific document.
    Checks Supabase shared registry first, then local SQLite.
    Useful for the UI to show which rules came from which circular.
    """
    # Try Supabase first
    try:
        from core.supabase_client import fetch_rules_for_document, _supabase_available
        if _supabase_available():
            rules = fetch_rules_for_document(document_name)
            if rules:
                return {
                    "document": document_name,
                    "source": "supabase",
                    "total": len(rules),
                    "rules": rules,
                }
    except Exception as e:
        logger.warning(f"[API] Supabase registry query failed: {e}")

    # Fallback to local SQLite
    try:
        from core.sqlite_client import RuleRegistrySQLite
        db = RuleRegistrySQLite()
        rules = db.fetch_by_source_document(document_name)
        return {
            "document": document_name,
            "source": "sqlite",
            "total": len(rules),
            "rules": rules,
        }
    except Exception as e:
        logger.error(f"[API] SQLite query failed: {e}")
        return {"document": document_name, "source": "none", "total": 0, "rules": []}


# ── /rules/status-summary ─────────────────────────────────────────────────

@app.get("/rules/status-summary")
async def rules_status_summary():
    """
    Return count of rules by status (NEW, EXISTING, MODIFIED, etc.).
    Used by UI dashboard to show provenance statistics.
    """
    try:
        from core.sqlite_client import RuleRegistrySQLite
        db = RuleRegistrySQLite()
        return db.get_status_summary()
    except Exception as e:
        return {"error": str(e)}


# ── Shared Registry Sync Helpers ──────────────────────────────────────────

def _sync_rules_to_shared_registry(
    rules: list,
    filename: str,
    document_type: str,
    document_date,
):
    """
    FEATURE 1 — Shared Supabase Cloud Registry.
    Persist rules to both SQLite (local) and Supabase (shared cross-bank cloud).
    EXISTING rules are NOT re-inserted (their provenance was already updated
    inside the delta_analyzer via update_rule_provenance).
    """
    import uuid as _uuid
    from core.sqlite_client import RuleRegistrySQLite
    from core.supabase_client import insert_or_update_rule, _supabase_available

    sqlite_db = RuleRegistrySQLite()
    supabase_ok = _supabase_available()

    # Rules to actually insert (not EXISTING — those are already in DB)
    insertable_statuses = {"NEW", "MODIFIED", "SUPERSEDED", "CLARIFICATION"}

    supabase_saved = 0
    sqlite_saved = 0

    for rule in rules:
        status = rule.get("status", "NEW")

        # Ensure rule always has a valid rule_id
        if not rule.get("rule_id"):
            if rule.get("id"):
                rule["rule_id"] = str(rule["id"])
            else:
                rule["rule_id"] = str(_uuid.uuid4())

        # Always stamp source document metadata
        rule.setdefault("source_document_name", filename)
        rule.setdefault("source_document_type", document_type)
        rule.setdefault("source_document_date", str(document_date) if document_date else None)

        # Always sync to SQLite (local)
        try:
            sqlite_db.upsert_rule(rule)
            sqlite_saved += 1
        except Exception as e:
            logger.warning(f"[API] SQLite sync failed for '{rule.get('title', '?')}': {e}")

        # Sync to Supabase shared registry (only insertable statuses)
        if status in insertable_statuses and supabase_ok:
            try:
                insert_or_update_rule(rule)
                supabase_saved += 1
            except Exception as e:
                logger.error(
                    f"[API] ❌ Supabase sync FAILED for rule '{rule.get('title', '?')}' "
                    f"(rule_id={rule.get('rule_id')}): {e}"
                )

    logger.info(
        f"[API] Sync complete for '{filename}': "
        f"{sqlite_saved}/{len(rules)} → SQLite | "
        f"{supabase_saved}/{sum(1 for r in rules if r.get('status','NEW') in insertable_statuses)} → Supabase"
    )


def _record_document_stats(
    filename: str,
    document_type: str,
    document_date,
    status_summary: dict,
):
    """Record per-document ingestion stats to both SQLite and Supabase."""
    import uuid as _uuid
    doc_record = {
        "id": str(_uuid.uuid4()),
        "filename": filename,
        "document_type": document_type,
        "document_date": document_date,
        "total_rules_extracted": sum(status_summary.values()),
        "new_rules": status_summary.get("NEW", 0),
        "modified_rules": status_summary.get("MODIFIED", 0),
        "existing_rules": status_summary.get("EXISTING", 0),
        "superseded_rules": status_summary.get("SUPERSEDED", 0),
        "clarification_rules": status_summary.get("CLARIFICATION", 0),
    }
    try:
        from core.sqlite_client import RuleRegistrySQLite
        RuleRegistrySQLite().upsert_ingestion_document(doc_record)
    except Exception as e:
        logger.warning(f"[API] SQLite ingestion_doc record failed: {e}")

    try:
        from core.supabase_client import record_ingestion_document, _supabase_available
        if _supabase_available():
            record_ingestion_document(doc_record)
    except Exception as e:
        logger.warning(f"[API] Supabase ingestion_doc record failed: {e}")


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


# ── /validate — Phase 2: Transaction Pipeline + Rule-Based Compliance Check ─

_latest_txn_result: dict = {}  # stores last transaction run for /violations


@app.post("/validate")
async def validate_transactions(request: Request):
    """
    Phase 2 - Transaction Compliance Engine:
    Stage 1: Parse CSV/XLS/XLSX
    Stage 2: Preprocess + data quality checks
    Stage 3: Store clean data to SQLite
    Stage 4: Load ALL rules from Supabase (master_direction + circular)
    Stage 5: Check EVERY row against EVERY rule (deterministic - no hallucinations)
    Returns per-row compliance report with clear violations for each rule.
    """
    global _latest_txn_result

    try:
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

    txn_dir = Path(settings.transaction_csv_dir)
    txn_dir.mkdir(parents=True, exist_ok=True)
    dest = txn_dir / (upload.filename or "upload.csv")

    logger.info(f"[API] /validate received: {upload.filename} ({upload.content_type})")

    try:
        content = await upload.read()
        dest.write_bytes(content)

        # ── Stages 1-3: Parse → Preprocess → Store ───────────────────────────
        logger.info(f"[API] Stage 1-3: Running pipeline on {upload.filename} ({len(content):,} bytes)")
        result = await run_transaction_pipeline_async(str(dest))

        # ── Stage 4: Load ALL rules from Supabase ────────────────────────────
        loop = asyncio.get_event_loop()

        def _load_all_rules():
            try:
                from core.supabase_client import fetch_all_rules, _supabase_available
                if _supabase_available():
                    rules = fetch_all_rules()
                    logger.info(f"[API] Stage 4: Loaded {len(rules)} rules from Supabase")
                    return rules
                logger.warning("[API] Supabase unavailable — using in-memory rules")
                return []
            except Exception as exc:
                logger.error(f"[API] Stage 4 failed to load rules: {exc}")
                return []

        all_rules = await loop.run_in_executor(None, _load_all_rules)

        # ── Stage 5: Check each row against every rule ───────────────────────
        if all_rules:
            def _run_rule_check():
                from transactions.file_parser import FileParsingPipeline
                from transactions.preprocessor import DataPreprocessingPipeline
                from transactions.rule_checker import check_all_transactions
                try:
                    parser = FileParsingPipeline(str(dest))
                    df_raw = parser.parse()
                    preprocessor = DataPreprocessingPipeline(df_raw)
                    df_clean, _ = preprocessor.run()
                    logger.info(
                        f"[API] Stage 5: Checking {len(df_clean)} rows "
                        f"against {len(all_rules)} rules"
                    )
                    return check_all_transactions(df_clean, all_rules, max_rows=500000)
                except Exception as exc:
                    logger.error(f"[API] Stage 5 rule-check failed: {exc}")
                    return {
                        "total_rows": 0, "rows_checked": 0,
                        "compliant_count": 0, "violation_count": 0,
                        "compliance_rate": 0.0,
                        "violations": [], "compliant_transactions": [],
                        "rule_violation_summary": {}, "rules_applied": 0,
                    }

            compliance_result = await loop.run_in_executor(None, _run_rule_check)

            # Merge data-quality violations + rule-based violations
            pipeline_violations = result.get("violations", [])
            rule_violations = compliance_result.get("violations", [])
            all_violations = pipeline_violations + rule_violations

            result.update({
                "rule_check_enabled": True,
                "rules_applied": compliance_result.get("rules_applied", 0),
                "rows_checked": compliance_result.get("rows_checked", 0),
                "compliant_count": compliance_result.get("compliant_count", 0),
                "violation_count": compliance_result.get("violation_count", 0),
                "compliance_rate": compliance_result.get("compliance_rate", 100.0),
                "violations": all_violations,
                "violations_count": len(all_violations),
                "compliant_transactions": compliance_result.get("compliant_transactions", []),
                "rule_violation_summary": compliance_result.get("rule_violation_summary", {}),
            })

            logger.info(
                f"[API] ✅ Stage 5 complete: "
                f"{compliance_result.get('violation_count', 0)} rows violated, "
                f"{compliance_result.get('compliant_count', 0)} compliant, "
                f"rate={compliance_result.get('compliance_rate', 0)}%"
            )
        else:
            logger.warning("[API] Stage 4: No rules loaded — skipping rule check")
            result["rule_check_enabled"] = False
            result["rule_check_warning"] = (
                "No compliance rules found. "
                "Upload a Master Direction PDF first to populate the rules registry."
            )
            result.setdefault("compliance_rate", 100.0)
            result.setdefault("compliant_transactions", [])
            result.setdefault("rule_violation_summary", {})

        _latest_txn_result = result
        logger.info(
            f"[API] /validate complete: "
            f"{result.get('rows_stored', 0)} rows stored, "
            f"{result.get('violations_count', 0)} violations, "
            f"compliance={result.get('compliance_rate', 'N/A')}%"
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
            id=v.get("id", f"VIO-{i+1:03d}"),
            transactionId=v.get("transactionId", f"TXN-{i+1:04d}"),
            amount=v.get("amount", 0.0),
            rule=v.get("rule", "Unknown Rule"),
            severity=v.get("severity", "MEDIUM"),
            page=None,
            status=v.get("status", v.get("verdict", "VIOLATION")),
            rule_id=v.get("rule_id", None)
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
    Returns a highly detailed pure-Python PDF compliance report written by Mistral 7B via AWS Bedrock.
    """
    import boto3
    import json
    from fastapi.responses import Response

    from core.supabase_client import get_supabase
    
    pdf_name = _latest_result.get("pdf_name", "unknown")
    rules = _latest_result.get("rules", [])
    
    # Pull the exact transaction validation results rather than initial rule extraction results
    violations_raw = _latest_txn_result.get("violations", [])
    violations = [v.model_dump() if hasattr(v, "model_dump") else (v if isinstance(v, dict) else vars(v)) for v in violations_raw]

    # Dynamically extract all violated `rule_id`s directly from the violations object list
    unique_rule_ids = list({v.get("rule_id") for v in violations if v.get("rule_id")})
    full_rules_context = []
    
    # Fetch the deep schema definition for each violated rule directly from Supabase's rules_registry
    if unique_rule_ids:
        try:
            supa = get_supabase()
            if supa:
                res = supa.table("rules_registry").select("*").in_("rule_id", unique_rule_ids).execute()
                if hasattr(res, 'data') and res.data:
                    full_rules_context = res.data
        except Exception as e:
            logger.error(f"Supabase context fetch for PDF failed: {e}")

    # Limit to avoid token blast
    rules_sample = json.dumps(rules[:15]) if rules else "No rules provided."
    viols_sample = json.dumps(violations[:25]) if violations else "No violations found."
    supabase_rules_sample = json.dumps(full_rules_context) if full_rules_context else "No deep rules registry found."

    prompt_context = f"File Analyzed: {pdf_name}\n\n[DETECTED VIOLATIONS]\n{viols_sample}\n\n[DEEP RULES REGISTRY CONTEXT FOR VIOLATED RULES]\n{supabase_rules_sample}"

    prompt = f"""You are PolicyGuard AI, an expert enterprise regulatory auditor.
Your task is to write a highly detailed, professional compliance audit report analyzing the rules extracted and the specific transaction violations detected in the provided system output. Explain the logic of the violations and summarize the risk landscape.
CRITICAL INSTRUCTION: You MUST explicitly list out each violated transaction using its exact Transaction ID (e.g., TXN-...) and clearly pair it with the deep rule context logic from the [DEEP RULES REGISTRY CONTEXT FOR VIOLATED RULES] section. Ensure all references map back exactly to their corresponding Supabase DB constraint parameters (e.g. condition_field, condition_operator, plain_english).

Output your entire response as properly formatted HTML (only the inner body content, without <html>, <head>, or <body> tags). Use <h2> for major sections, <h3> for subsections, <p> for detailed paragraphs, and <ul>/<li> for lists. Do not use markdown blocks.

SYSTEM OUTPUT LOGS:
{prompt_context}"""

    try:
        # Utilize the global LLM router which handles the specific API proxy & failover credentials
        llm_html = llm_router.route_prompt(prompt, fallback_provider="bedrock")
        if not llm_html:
            raise ValueError("All LLM providers failed to generate the report.")
    except Exception as e:
        logger.error(f"LLM explainability invocation failed: {e}")
        llm_html = f"<h2>Compliance Report for {pdf_name}</h2><p>Error generating deep explainability report via LLM Router: {e}</p><p>Rules Extracted: {len(rules)}</p><p>Violations Detected: {len(violations)}</p>"

    html_string = f"""
    <html>
      <head>
        <style>
          body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; padding: 40px; color: #1a1a1a; }}
          .header {{ text-align: center; border-bottom: 3px solid #FF6600; padding-bottom: 20px; margin-bottom: 30px; }}
          .header h1 {{ margin: 0; color: #000080; font-size: 28px; text-transform: uppercase; letter-spacing: 2px; }}
          .header p {{ margin: 5px 0 0 0; color: #666; font-size: 14px; }}
          h2 {{ color: #138808; border-bottom: 1px solid #ccc; padding-bottom: 5px; margin-top: 30px; }}
          h3 {{ color: #000080; }}
          p {{ line-height: 1.6; font-size: 14px; text-align: justify; }}
          ul, li {{ font-size: 14px; line-height: 1.6; }}
          table {{ width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 15px; }}
          th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 13px; }}
          th {{ background-color: #f8f9fa; color: #000080; }}
          .footer {{ text-align: center; margin-top: 50px; font-size: 10px; color: #999; border-top: 1px solid #eee; padding-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="header">
            <h1>PolicyGuard AI</h1>
            <p>Enterprise Compliance Explainability Audit</p>
            <p><strong>Document:</strong> {pdf_name}</p>
        </div>
        
        {llm_html}

        <div class="footer">
            Generated by PolicyGuard AI Validation Pipeline &bull; Powered by AWS Bedrock Mistral 7B
        </div>
      </body>
    </html>
    """

    try:
        from xhtml2pdf import pisa
        import io
        pdf_bytes_io = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=pdf_bytes_io)
        if pisa_status.err:
            logger.error(f"xhtml2pdf rendering error.")
            pdf_bytes = b"PDF Generation Failed"
        else:
            pdf_bytes = pdf_bytes_io.getvalue()
    except Exception as e:
        logger.error(f"xhtml2pdf failed: {e}")
        pdf_bytes = b"PDF Generation Failed"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=policyguard-compliance-report.pdf"}
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
