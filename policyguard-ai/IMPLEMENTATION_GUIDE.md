# PolicyGuard AI - 8-Layer PDF Ingestion Pipeline v2.0

## Overview

A production-ready PDF policy extraction system with 8 specialized processing layers. Handles digital PDFs, scanned images, and mixed documents. Automatically routes across multiple LLM providers with rate-limit failover.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      8-LAYER PIPELINE ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Layer 1:  [PDF Classifier]       ← Detect digital/scanned/mixed         │
│  Layer 2:  [Semantic Chunker]     ← Split at paragraph boundaries        │
│  Layer 3:  [Chunk Filter]         ← Drop forms/tables (save 30% calls)   │
│  Layer 4:  [Adaptive Batcher]     ← Fill calls to 80% context limit      │
│  Layer 5:  [Async LLM Router]     ← Together→OpenRouter→Groq failover    │
│  Layer 6:  [Two-Pass Verifier]    ← Re-check CRITICAL rules vs source    │
│  Layer 7:  [Cache + SSE]          ← Instant repeats + UI progress        │
│  Layer 8:  [Dedup + Confidence]   ← Auto-approve ≥0.85 confidence        │
│                                                                          │
│  OUTPUT → Supabase + ChromaDB + rules.json                              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt

# For scanned/image PDF support (optional)
pip install pytesseract pdf2image
# Also install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. Configuration

Update `.env` with your API keys:

```env
# LLM Providers (configure at least one)
TOGETHER_API_KEY=your_together_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Supabase (for rule storage)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Paths
POLICY_PDF_DIR=./data/policy_pdfs
CACHE_DIR=./registry/cache
```

### 3. Run the API Server

```bash
cd api
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000/docs` for interactive API documentation.

### 4. Upload a PDF

```bash
curl -X POST \
  -F "file=@policy.pdf" \
  http://localhost:8000/extract
```

Or use the interactive Swagger UI at `/docs`.

---

## Layer Details

### Layer 1: PDF Classifier

**Purpose:** Detects whether PDF is digital (searchable text), scanned (images), or mixed.

**Why it matters:** PyMuPDF fails silently on scanned PDFs, extracting 0 rules. This layer routes to OCR automatically.

**How it works:**
- Opens PDF with PyMuPDF
- Counts pages with ≥100 chars of extracted text
- Checks for images on low-text pages
- Classifies as: DIGITAL (≥85% text) | SCANNED (≤15% text) | MIXED (15-85%)

**Code:**
```python
from agents.pdf_classifier import classify_pdf, extract_text_by_type

classification = classify_pdf("policy.pdf")
# Returns: {type: "digital", total_pages: 20, text_pages: 19, ...}

pages = extract_text_by_type("policy.pdf", classification)
# Returns: [{page: 1, text: "..."}, ...]
```

**Cost savings:** Avoids ~20% wasted API calls on image-heavy PDFs.

---

### Layer 2: Semantic Paragraph Chunker

**Purpose:** Splits pages at meaningful boundaries (paragraphs, sections) instead of arbitrary character counts.

**Why it matters:** RecursiveCharacterTextSplitter cuts rules in half mid-sentence. This layer preserves complete thoughts.

**How it works:**
- Splits on double newlines (paragraph breaks)
- Detects section markers (e.g., "Para 21", "3.1", "(a)")
- Groups paragraphs into chunks up to 800 tokens
- Never cuts in middle of sentence

**Code:**
```python
from core.semantic_chunker import semantic_chunk_pages

chunks = semantic_chunk_pages(pages)
# Returns: [{text: "full paragraph...", page: 1, chunk_index: 0, ...}, ...]
```

**Output structure:**
```json
{
  "text": "Full semantic chunk text...",
  "page": 1,
  "chunk_index": 0,
  "paragraph_number": "Para 18",
  "char_count": 1250,
  "metadata": {
    "page": 1,
    "chunk_index": 0,
    "source": "page_1_chunk_0"
  }
}
```

---

### Layer 3: Chunk Filter

**Purpose:** Drops non-policy content (forms, tables, appendices) BEFORE sending to LLM.

**Why it matters:** Saves ~30% of API calls by filtering forms/tables locally.

**How it works:**
- Detects table patterns (|...|...|)
- Detects form fields (Name:___, Date:___)
- Detects appendices ("Annex-VI", "Schedule A")
- Drops chunks with <40% alphabetic content
- Requires minimum 100 chars

**Code:**
```python
from core.chunk_filter import filter_chunks, should_skip_chunk

filtered, skipped = filter_chunks(chunks)
# 100 chunks → 70 chunks (30% skipped as forms/tables)
```

---

### Layer 4: Adaptive Batcher

**Purpose:** Packs chunks efficiently into LLM calls to use 80% of context limit.

**Why it matters:** Prevents context overflow and optimizes costs:
- Small 10-page PDF: 1 call
- Medium 80-page PDF: 8 calls
- Large 300-page PDF: 30 calls

**How it works:**
- Calculates available tokens (provider limit - system prompt - output reserve)
- Fills each batch to 80% of limit
- Falls back if single chunk exceeds limit
- Logs token usage per batch

**Code:**
```python
from core.adaptive_batcher import adaptive_batch_chunks

batches = adaptive_batch_chunks(filtered_chunks, provider="together")
# 50 chunks → 5 batches (10 chunks/batch avg)
```

**Per-provider limits:**
- Together AI: 6000 tokens available
- OpenRouter: 6000 tokens available
- Groq: 3000 tokens available (slower API)

---

### Layer 5: Parallel Async LLM Router

**Purpose:** Routes extraction across multiple LLM providers with automatic failover and rate-limit handling.

**Why it matters:**
- Primary fails? Switches to secondary automatically
- No manual error handling needed
- Respects RPM limits per provider
- 5-8 concurrent calls per provider

**How it works:**
1. Primary provider: Together AI (600 RPM, $25 free credits)
2. Falls back to: OpenRouter (100 RPM, auto-routes)
3. Final fallback: Groq (30 RPM, Mixtral-8x7b)

**Code:**
```python
from agents.llm_router import LLMRouter

router = LLMRouter()  # Auto-initializes with configured providers

result = await router.extract_all_batches_async(
    batches,
    system_prompt="Extract rules from policy text...",
    progress_cb=async_progress_callback,  # SSE updates
)
# Returns: {rules: [...], total: 47, provider: "together", ...}
```

**Rate limit handling:**
```
Batch 1-8:  Together AI ✓
Batch 9:    Together AI [429 Rate Limit]
Batch 9→:   Switch to OpenRouter
Batch 15:   OpenRouter [rate limit]
Batch 15→:  Switch to Groq
```

---

### Layer 6: Two-Pass Verifier

**Purpose:** Re-checks CRITICAL and HIGH severity rules against actual page text to catch hallucinations.

**Why it matters:**
- LLMs hallucinate thresholds ("5 years" when document says "3 years")
- Catches wrong source clauses
- Only re-verifies HIGH/CRITICAL rules to save cost

**How it works:**
1. For each CRITICAL/HIGH rule:
   - Fetches source page text
   - Asks LLM: "Does this rule actually appear in the page?"
   - Verifies thresholds match exactly
2. Returns rules with status:
   - `verified`: Source found, thresholds correct
   - `correction_needed`: Source found but values wrong
   - `source_not_found`: Hallucinated, marked inactive

**Code:**
```python
from core.two_pass_verifier import TwoPassVerifier

verifier = TwoPassVerifier(pages)
verified_rules = verifier.verify_critical_rules(extracted_rules)

# Check status
for rule in verified_rules:
    print(f"{rule['title']}: {rule['verification_status']}")
    # Options: verified, correction_needed, source_not_found, error_verify
```

---

### Layer 7: Cache + SSE Progress

**Purpose:** 
- Same PDF uploaded twice → **instant response** (0.1s vs 30s)
- Frontend shows real-time progress: "Extracting... 15% complete"

**How it works:**

#### File-Based Cache
```python
from core.cache import get_pdf_hash, get_cached_rules, cache_rules

# Compute unique ID
pdf_hash = get_pdf_hash("large_policy.pdf")
# Returns: "a1b2c3d4e5f6g7h8"

# Check cache
cached = get_cached_rules(pdf_hash)
if cached:
    return cached  # Instant response!

# ... extract rules ...

# Save for next time
cache_rules(pdf_hash, rules)
```

#### SSE Progress Stream
Frontend connects to `/progress/{session_id}` and receives:

```javascript
// Frontend code
const eventSource = new EventSource('/progress/abc123');
eventSource.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(update);
  // {stage: "extraction", percent: 25, rules_found: 12, ...}
};
```

Server publishes:
```python
await queue.put({
    "stage": "extraction",
    "completed": 5,
    "total": 20,
    "percent": 25,
    "rules_found": 12,
    "provider": "together",
})
```

---

### Layer 8: Dedup + Confidence Validator

**Purpose:**
- Remove duplicate rules (same rule extracted twice)
- Auto-approve rules with confidence ≥0.85
- Flag lower-confidence rules for human review

**How it works:**

#### Deduplication
```python
from core.dedup_validator import deduplicate_rules

rules = [
    {title: "KYC Requirement", severity: "CRITICAL", confidence: 0.95},
    {title: "KYC Requirement", severity: "CRITICAL", confidence: 0.90},  # Dup
    {title: "AML Screening", severity: "HIGH", confidence: 0.88},
]

deduped, removed = deduplicate_rules(rules)
# 3 rules → 2 rules (keeps highest confidence version of each)
```

#### Confidence Validation
```python
from core.dedup_validator import apply_confidence_validation

auto_approved, flagged = apply_confidence_validation(rules)

# auto_approved: Rules with confidence ≥ 0.85 (automatically approved)
# flagged: Rules with confidence < 0.85 (need human review)
```

**Approval workflow:**
```
Rule 1: "KYC Requirement" → confidence 0.95 → AUTO-APPROVED ✓
Rule 2: "AML Screening"   → confidence 0.85 → AUTO-APPROVED ✓
Rule 3: "Manual Review"   → confidence 0.72 → PENDING REVIEW 🔄
```

---

## API Endpoints

### POST /extract

Upload PDF and extract rules (returns immediately with progress).

**Request:**
```bash
curl -X POST -F "file=@policy.pdf" http://localhost:8000/extract
```

**Response:**
```json
{
  "session_id": "a1b2c3d4",
  "pdf_name": "policy.pdf",
  "total_rules": 47,
  "auto_approved": 42,
  "pending_review": 5,
  "from_cache": false,
  "processing_time_seconds": 28.4,
  "rules": [
    {
      "id": "r1",
      "title": "KYC Requirement",
      "description": "All customers must undergo Know Your Customer verification...",
      "severity": "CRITICAL",
      "source_clause": "Para 18: NBFCs shall perform...",
      "page_number": 5,
      "confidence_score": 0.95,
      "is_approved": true,
      "approval_status": "auto_approved"
    }
  ],
  "statistics": {
    "total_pages": 20,
    "total_chunks": 85,
    "filtered_chunks": 60,
    "batches": 6,
    "extracted_rules": 52,
    "verified_rules": 50,
    "final_rules": 47,
    "auto_approved": 42,
    "pending_review": 5,
    "processing_seconds": 28.4
  }
}
```

### GET /progress/{session_id}

Server-Sent Events stream for real-time progress updates.

**Usage:**
```javascript
const eventSource = new EventSource('/progress/a1b2c3d4');
eventSource.onmessage = (e) => console.log(JSON.parse(e.data));
```

**Events:**
```json
{stage: "classification", pdf_type: "digital", text_pages: 20}
{stage: "extraction", pages_extracted: 20}
{stage: "chunking", chunks_created: 85}
{stage: "filtering", chunks_remaining: 60}
{stage: "batching", batches_created: 6}
{stage: "extraction", completed: 2, total: 6, percent: 33}
{stage: "llm_complete", rules_extracted: 52, provider: "together"}
{stage: "verification", rules_verified: 50}
{stage: "deduplication", rules_final: 47}
{stage: "validation", auto_approved: 42}
```

### GET /health

Health check endpoint.

```bash
curl http://localhost:8000/health
# {status: "healthy", router_ready: true, app_env: "development"}
```

---

## Testing

### Run Single Layer Tests

```bash
# Test Layer 1: PDF Classifier
python -c "
from agents.pdf_classifier import classify_pdf
result = classify_pdf('data/policy_pdfs/sample.pdf')
print(result)
"
```

### Run Full Pipeline Test

```bash
python tests/test_8layer_pipeline.py data/policy_pdfs/sample.pdf

# Output:
# ============================================================
# POLICYGUARD AI - 8-LAYER PIPELINE TESTS
# ============================================================
# 
# LAYER 1: PDF CLASSIFIER
# ✓ PDF Type: digital
# ✓ Total Pages: 20
# ...
# ✓ All tests passed
```

### Run with pytest

```bash
pytest tests/ -v

# Tests Layer 1-8
# Tests API endpoints
# Tests cache behavior
```

---

## Environment Variables

```env
# ════════════════════════════════════════════════════════════════
# LLM PROVIDERS (configure at least one)
# ════════════════════════════════════════════════════════════════

# Together AI - Primary provider (600 RPM, free tier available)
TOGETHER_API_KEY=key_XXX

# OpenRouter - Secondary (auto-routes to various models)
OPENROUTER_API_KEY=sk-or-v1-XXX

# Groq - Fallback (30 RPM, free tier)
GROQ_API_KEY=gsk_XXX

# HuggingFace
HUGGINGFACE_API_TOKEN=hf_XXX

# ════════════════════════════════════════════════════════════════
# SUPABASE (Rule storage)
# ════════════════════════════════════════════════════════════════
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# ════════════════════════════════════════════════════════════════
# CHROMA DB (Vector embeddings)
# ════════════════════════════════════════════════════════════════
CHROMA_PERSIST_DIR=./vector_store
CHROMA_COLLECTION_NAME=policy_clauses
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# ════════════════════════════════════════════════════════════════
# PATHS
# ════════════════════════════════════════════════════════════════
POLICY_PDF_DIR=./data/policy_pdfs
TRANSACTION_CSV_DIR=./data/transactions
REPORTS_DIR=./reports
CACHE_DIR=./registry/cache

# ════════════════════════════════════════════════════════════════
# APPLICATION
# ════════════════════════════════════════════════════════════════
APP_ENV=development
LOG_LEVEL=INFO
PRIMARY_PROVIDER=together
ENABLE_VERIFICATION=true
VERIFICATION_PROVIDER=groq
```

---

## Performance Metrics

### Layer Processing Time (10-page PDF)

| Layer | Time | Cost |
|-------|------|------|
| 1. Classifier | <1s | $0 |
| 2. Chunker | <1s | $0 |
| 3. Filter | <1s | $0 |
| 4. Batcher | <1s | $0 |
| 5. LLM Extraction | ~8s | $0.10 |
| 6. Verification | ~2s | $0.02 |
| 7. Cache | instant | $0 |
| 8. Dedup+Validation | <1s | $0 |
| **Total** | **~13s** | **$0.12** |

### Scaling

| PDF Size | Pages | Chunks | Batches | API Calls | Time | Cost |
|----------|-------|--------|---------|-----------|------|------|
| Small | 10 | 20 | 2 | 2 | 13s | $0.12 |
| Medium | 80 | 160 | 16 | 16 | 2m | $0.80 |
| Large | 300 | 600 | 60 | 60 | 8m | $2.40 |

### Cache Hits

Same PDF uploaded again → **0.1 seconds** (instant response from cache)

---

## Troubleshooting

### Issue: "No LLM provider configured"

**Solution:** Set at least one API key in `.env`:
```env
TOGETHER_API_KEY=key_XXX
# or
OPENROUTER_API_KEY=sk-or-v1-XXX
GROQ_API_KEY=gsk_XXX
```

### Issue: "Scanned pages will be skipped"

**Solution:** Install OCR support:
```bash
pip install pytesseract pdf2image
# Install Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki
```

### Issue: "Rate limit on provider X"

**Solution:** Router automatically fails over to next provider. Check `/health` to verify multiple providers are configured.

### Issue: "Low confidence rules not auto-approved"

**Solution:** Confidence >= 0.85 required for auto-approval. Rules below this threshold are flagged for human review.

---

## Advanced Usage

### Custom System Prompt

In `api/main.py`, modify `_build_system_prompt()`:

```python
def _build_system_prompt() -> str:
    return """You are a compliance analyst.
    
Extract specific types of rules only: validation rules, approval thresholds, etc.
...
"""
```

### Custom Rule Scoring

Modify `core/dedup_validator.py` confidence logic:

```python
# Auto-approve at different thresholds by severity
if rule.get("severity") == "CRITICAL" and confidence >= 0.80:
    return True
elif rule.get("severity") == "HIGH" and confidence >= 0.85:
    return True
```

### Disable Verification Step

In `.env`:
```env
ENABLE_VERIFICATION=false
```

---

## Architecture Diagram

```
┌──────────────────┐
│  User Uploads    │
│  PDF via /upload │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 1] PDF Classifier             │
│ Detects: digital / scanned / mixed   │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 2] Semantic Chunker           │
│ Splits at paragraph boundaries       │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 3] Chunk Filter               │
│ Drops forms/tables (30% reduction)   │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 4] Adaptive Batcher           │
│ Token-aware batching (80% fill)      │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 5] Parallel Async LLM Router  │
│ Together→OpenRouter→Groq failover    │
│ 5-8 concurrent calls per provider    │
│         SSE Progress → UI            │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 6] Two-Pass Verifier          │
│ Re-check CRITICAL/HIGH vs source     │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐         ┌────────────────┐
│ [Layer 7] Cache                      │────────→│ Same PDF next  │
│ File-based cache (instant repeat)    │         │ time: 0.1s     │
└────────┬─────────────────────────────┘         └────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ [Layer 8] Dedup + Confidence         │
│ Remove duplicates                    │
│ Auto-approve ≥0.85 confidence        │
│ Flag <0.85 for review                │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Output: JSON Response                │
│ + Supabase + ChromaDB + Cache        │
└──────────────────────────────────────┘
```

---

## File Structure

```
policyguard-ai/
├── api/
│   └── main.py                      ← FastAPI app with all endpoints
├── agents/
│   ├── pdf_classifier.py            ← Layer 1
│   └── llm_router.py                ← Layer 5
├── core/
│   ├── config.py                    ← Configuration
│   ├── semantic_chunker.py          ← Layer 2
│   ├── chunk_filter.py              ← Layer 3
│   ├── adaptive_batcher.py          ← Layer 4
│   ├── two_pass_verifier.py         ← Layer 6
│   ├── cache.py                     ← Layer 7
│   ├── dedup_validator.py           ← Layer 8
│   └── logger.py                    ← Logging
├── tests/
│   └── test_8layer_pipeline.py      ← Integration tests
├── data/
│   └── policy_pdfs/                 ← Input PDFs
├── registry/
│   ├── cache/                       ← File-based cache
│   └── rules.json                   ← Rule registry
├── .env                             ← Configuration
└── requirements.txt                 ← Dependencies
```

---

## Performance Optimization Tips

1. **Increase batch size** for faster processing (use more context):
   - Edit `core/adaptive_batcher.py`: `MAX_TOKENS_PER_CHUNK = 1200`

2. **Reduce verification overhead**:
   - Set `ENABLE_VERIFICATION=false` to skip Layer 6

3. **Use Together AI** as primary (fastest, 600 RPM):
   - Set `PRIMARY_PROVIDER=together`

4. **Enable caching**:
   - Same PDF = instant response (sub-second)

5. **Filter aggressively** in Layer 3:
   - Modify patterns to drop more non-policy content

---

## Future Enhancements

- [ ] Redis cache instead of file-based
- [ ] Multi-PDF batch processing
- [ ] Custom LLM model support
- [ ] Rule versioning / tracking changes
- [ ] Web UI for rule management
- [ ] Analytics dashboard
- [ ] Webhook notifications on completion

---

## License

Proprietary - PolicyGuard AI

## Support

Contact: support@policyguard.ai
