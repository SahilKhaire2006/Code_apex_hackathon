# Quick Start Guide - PolicyGuard AI 8-Layer Pipeline

## 5-Minute Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure .env
```bash
# Edit .env file and add/verify:
GROQ_API_KEY=your_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
TOGETHER_API_KEY=your_together_api_key_here
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_anon_key_here
```

### 3. Create Required Directories
```bash
mkdir -p data/policy_pdfs
mkdir -p registry/cache
mkdir -p logs
mkdir -p reports
```

### 4. Start the API Server
```bash
cd api
python main.py

# Server starts at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 5. Upload and Extract
```bash
# Option A: Using curl
curl -X POST \
  -F "file=@your_policy.pdf" \
  http://localhost:8000/extract

# Option B: Using Python
import requests
with open("policy.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/extract",
        files={"file": f}
    )
    rules = response.json()
    print(f"Extracted {rules['total_rules']} rules")

# Option C: Interactive Swagger UI
# Visit http://localhost:8000/docs
```

---

## Module-by-Module Usage

### Using Individual Layers

```python
# ═══════════════════════════════════════════════════════════════
# Layer 1: PDF Classifier
# ═══════════════════════════════════════════════════════════════
from agents.pdf_classifier import classify_pdf, extract_text_by_type

# Detect PDF type
classification = classify_pdf("policy.pdf")
print(f"Type: {classification['type']}")  # digital / scanned / mixed

# Extract text appropriately
pages = extract_text_by_type("policy.pdf", classification)
print(f"Extracted {len(pages)} pages")


# ═══════════════════════════════════════════════════════════════
# Layer 2: Semantic Chunker
# ═══════════════════════════════════════════════════════════════
from core.semantic_chunker import semantic_chunk_pages

chunks = semantic_chunk_pages(pages)
print(f"Created {len(chunks)} semantic chunks")


# ═══════════════════════════════════════════════════════════════
# Layer 3: Chunk Filter
# ═══════════════════════════════════════════════════════════════
from core.chunk_filter import filter_chunks

filtered, skipped = filter_chunks(chunks)
print(f"Kept {len(filtered)} chunks, skipped {skipped} forms/tables")


# ═══════════════════════════════════════════════════════════════
# Layer 4: Adaptive Batcher
# ═══════════════════════════════════════════════════════════════
from core.adaptive_batcher import adaptive_batch_chunks

batches = adaptive_batch_chunks(filtered, provider="together")
print(f"Packed into {len(batches)} token-aware batches")


# ═══════════════════════════════════════════════════════════════
# Layer 5: Async LLM Router
# ═══════════════════════════════════════════════════════════════
import asyncio
from agents.llm_router import LLMRouter

async def extract_rules():
    router = LLMRouter()
    result = await router.extract_all_batches_async(
        batches,
        system_prompt="Extract compliance rules...",
    )
    return result

result = asyncio.run(extract_rules())
print(f"Extracted {result['total']} rules using {result['provider']}")


# ═══════════════════════════════════════════════════════════════
# Layer 6: Two-Pass Verifier
# ═══════════════════════════════════════════════════════════════
from core.two_pass_verifier import TwoPassVerifier

verifier = TwoPassVerifier(pages)
verified = verifier.verify_critical_rules(result['rules'])
print(f"Verified {len(verified)} rules")


# ═══════════════════════════════════════════════════════════════
# Layer 7: Cache System
# ═══════════════════════════════════════════════════════════════
from core.cache import get_pdf_hash, get_cached_rules, cache_rules

pdf_hash = get_pdf_hash("policy.pdf")

# Check cache
cached = get_cached_rules(pdf_hash)
if cached:
    print(f"Found {len(cached)} cached rules!")
    
# Save to cache
cache_rules(pdf_hash, verified)
print(f"Cached {len(verified)} rules for next time")


# ═══════════════════════════════════════════════════════════════
# Layer 8: Dedup + Confidence Validation
# ═══════════════════════════════════════════════════════════════
from core.dedup_validator import deduplicate_rules, apply_confidence_validation

deduped, removed = deduplicate_rules(verified)
print(f"Removed {len(removed)} duplicate rules")

auto_approved, flagged = apply_confidence_validation(deduped)
print(f"Auto-approved: {len(auto_approved)}")
print(f"Pending review: {len(flagged)}")
```

---

## FastAPI Usage Examples

### Python Client

```python
import requests
import json

# Upload PDF and extract rules
with open("policy.pdf", "rb") as pdf:
    response = requests.post(
        "http://localhost:8000/extract",
        files={"file": pdf}
    )

data = response.json()
print(f"Session: {data['session_id']}")
print(f"Rules extracted: {data['total_rules']}")
print(f"Auto-approved: {data['auto_approved']}")
print(f"Pending review: {data['pending_review']}")

# Print rules
for rule in data['rules'][:5]:
    print(f"\n{rule['title']}")
    print(f"  Severity: {rule['severity']}")
    print(f"  Confidence: {rule['confidence_score']:.2f}")
    print(f"  Status: {rule['approval_status']}")
```

### JavaScript/TypeScript Client

```javascript
// Upload PDF
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/extract', {
  method: 'POST',
  body: formData
});

const data = await response.json();
console.log(`Extracted ${data.total_rules} rules`);

// Get session ID for progress tracking
const sessionId = data.session_id;

// Listen to progress updates
const eventSource = new EventSource(`/progress/${sessionId}`);

eventSource.onmessage = (event) => {
  const update = JSON.parse(event.data);
  
  switch(update.stage) {
    case 'extraction':
      updateProgressBar(update.percent);
      updateStatus(`Found ${update.rules_found} rules...`);
      break;
    case 'verification':
      updateStatus('Verifying critical rules...');
      break;
    case 'validation':
      updateStatus('Finalizing...');
      break;
  }
};

eventSource.onclose = () => {
  console.log('Processing complete');
  eventSource.close();
};
```

### cURL Examples

```bash
# ═══════════════════════════════════════════════════════════════
# Extract rules from PDF
# ═══════════════════════════════════════════════════════════════
curl -X POST \
  -F "file=@policy.pdf" \
  http://localhost:8000/extract | jq .

# Pretty print with jq
curl -X POST \
  -F "file=@policy.pdf" \
  http://localhost:8000/extract | jq '.rules[0:3]'

# Save to file
curl -X POST \
  -F "file=@policy.pdf" \
  http://localhost:8000/extract > results.json


# ═══════════════════════════════════════════════════════════════
# Monitor progress in real-time
# ═══════════════════════════════════════════════════════════════
curl -N http://localhost:8000/progress/abc123def456

# With jq for pretty printing
curl -N http://localhost:8000/progress/abc123def456 | jq '.'


# ═══════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════
curl http://localhost:8000/health | jq .
```

---

## Testing

### Run Integration Tests

```bash
# Full pipeline test (requires sample PDF)
python tests/test_8layer_pipeline.py data/policy_pdfs/sample.pdf

# Run pytest
pytest tests/test_8layer_pipeline.py -v

# Test specific layer
python -c "
from tests.test_8layer_pipeline import test_layer8_dedup
test_layer8_dedup()
"
```

### Manual Testing Workflow

```python
import time
from pathlib import Path

pdf_path = "data/policy_pdfs/test_policy.pdf"

# Start timer
start = time.time()

# Layer 1: Classify
from agents.pdf_classifier import classify_pdf, extract_text_by_type
classification = classify_pdf(pdf_path)
print(f"✓ Layer 1: {time.time()-start:.2f}s")

# Layer 2: Chunk
from core.semantic_chunker import semantic_chunk_pages
pages = extract_text_by_type(pdf_path, classification)
chunks = semantic_chunk_pages(pages)
print(f"✓ Layer 2: {time.time()-start:.2f}s")

# Layer 3: Filter
from core.chunk_filter import filter_chunks
filtered, _ = filter_chunks(chunks)
print(f"✓ Layer 3: {time.time()-start:.2f}s")

# Layer 4: Batch
from core.adaptive_batcher import adaptive_batch_chunks
batches = adaptive_batch_chunks(filtered)
print(f"✓ Layer 4: {time.time()-start:.2f}s")

# Layer 5: Extract (async)
import asyncio
from agents.llm_router import LLMRouter

async def test():
    router = LLMRouter()
    result = await router.extract_all_batches_async(
        batches,
        "Extract compliance rules from policy text..."
    )
    return result

result = asyncio.run(test())
print(f"✓ Layer 5: {time.time()-start:.2f}s - {len(result['rules'])} rules")

# Layer 6: Verify
from core.two_pass_verifier import TwoPassVerifier
verifier = TwoPassVerifier(pages)
verified = verifier.verify_critical_rules(result['rules'])
print(f"✓ Layer 6: {time.time()-start:.2f}s")

# Layer 7: Cache
from core.cache import get_pdf_hash, cache_rules
pdf_hash = get_pdf_hash(pdf_path)
cache_rules(pdf_hash, verified)
print(f"✓ Layer 7: {time.time()-start:.2f}s")

# Layer 8: Dedup + Validate
from core.dedup_validator import deduplicate_rules, apply_confidence_validation
deduped, _ = deduplicate_rules(verified)
auto_approved, flagged = apply_confidence_validation(deduped)
print(f"✓ Layer 8: {time.time()-start:.2f}s")

print(f"\n{'='*50}")
print(f"TOTAL TIME: {time.time()-start:.2f} seconds")
print(f"Rules extracted: {len(result['rules'])}")
print(f"After dedup: {len(deduped)}")
print(f"Auto-approved: {len(auto_approved)}")
print(f"Pending review: {len(flagged)}")
```

---

## Common Issues & Solutions

### Issue: "File not found" error
```
✗ PDF file not found: policy.pdf
```
**Solution:** Use absolute path or ensure file is in current directory
```bash
python -c "from pathlib import Path; print(Path.cwd())"
# Move PDF to current directory or use full path
```

### Issue: "No LLM provider configured"
```
✗ No LLM provider configured. Set TOGETHER_API_KEY, OPENROUTER_API_KEY, or GROQ_API_KEY
```
**Solution:** Add API keys to `.env`
```bash
nano .env
# Add:
# GROQ_API_KEY=your_key
```

### Issue: "Rate limit" errors
```
[together] Rate limit on batch 5
```
**Solution:** This is automatic and expected! Router switches to next provider:
```
[together] Rate limit
→ [openrouter] Processing batch 5
→ [groq] Processing final batches
```

### Issue: Slow processing
**Solution:** Optimize in order of impact:
1. Enable cache (first time is slow, repeats instant): `cache=enabled`
2. Use Together AI (fastest): `PRIMARY_PROVIDER=together`
3. Increase batch size: `MAX_TOKENS_PER_CHUNK=1200`
4. Disable verification: `ENABLE_VERIFICATION=false`

---

## API Response Format

```json
{
  "session_id": "abc123",
  "pdf_name": "policy.pdf",
  "total_rules": 47,
  "auto_approved": 42,
  "pending_review": 5,
  "from_cache": false,
  "processing_time_seconds": 28.4,
  "rules": [
    {
      "id": "r123",
      "title": "Customer Identity Verification",
      "description": "Customers must be verified before account opening...",
      "severity": "CRITICAL",
      "source_clause": "Para 5: All NBFCs shall...",
      "page_number": 3,
      "confidence_score": 0.96,
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

---

## Performance Targets

| Scenario | Expected Time | Cost |
|----------|---|---|
| **Cache Hit** (same PDF twice) | **0.1s** | **$0** |
| Small PDF (10 pages) | ~15s | $0.12 |
| Medium PDF (80 pages) | ~2m | $0.80 |
| Large PDF (300 pages) | ~8m | $2.40 |

**Cache hit is the key!** Most PDFs (policies, terms, etc.) stay the same.

---

## Next Steps

1. ✓ Install and setup (5 min)
2. ✓ Upload first PDF (1 min)
3. ✓ Review extracted rules
4. ✓ Check auto-approved vs pending
5. ✓ Customize confidence threshold if needed
6. ✓ Integrate with your application

---

## Getting Help

- **API Docs:** http://localhost:8000/docs
- **Implementation Guide:** `IMPLEMENTATION_GUIDE.md`
- **Layer Tests:** `python tests/test_8layer_pipeline.py`
- **Logs:** `cat logs/app.log`

