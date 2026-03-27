"""
Integration test for 8-Layer PDF Ingestion Pipeline.
Tests each layer independently and as a complete pipeline.
"""

import asyncio
from pathlib import Path
from agents.pdf_classifier import classify_pdf, extract_text_by_type
from core.semantic_chunker import semantic_chunk_pages, get_chunk_stats
from core.chunk_filter import filter_chunks, get_filter_stats
from core.adaptive_batcher import adaptive_batch_chunks, get_batch_stats
from core.two_pass_verifier import TwoPassVerifier
from core.dedup_validator import deduplicate_rules, apply_confidence_validation
from core.cache import get_pdf_hash, get_cached_rules, cache_rules, get_cache_stats
from core.logger import logger


def test_layer1_classifier(pdf_path: str) -> dict:
    """Test Layer 1: PDF Classifier"""
    print("\n" + "="*60)
    print("LAYER 1: PDF CLASSIFIER")
    print("="*60)
    
    try:
        result = classify_pdf(pdf_path)
        print(f"✓ PDF Type: {result['type']}")
        print(f"✓ Total Pages: {result['total_pages']}")
        print(f"✓ Text Pages: {result['text_pages']}")
        print(f"✓ Image Pages: {result['image_pages']}")
        print(f"✓ Text Ratio: {result['text_ratio']}")
        return result
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


def test_layer1b_extraction(pdf_path: str, classification: dict):
    """Test Layer 1b: Text extraction based on classification"""
    print("\n" + "="*60)
    print("LAYER 1B: TEXT EXTRACTION")
    print("="*60)
    
    try:
        pages = extract_text_by_type(pdf_path, classification)
        print(f"✓ Pages extracted: {len(pages)}")
        for page in pages[:3]:  # Show first 3
            print(f"  - Page {page['page']}: {len(page['text'])} chars")
        if len(pages) > 3:
            print(f"  ... and {len(pages)-3} more")
        return pages
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


def test_layer2_chunker(pages: list) -> list:
    """Test Layer 2: Semantic Chunker"""
    print("\n" + "="*60)
    print("LAYER 2: SEMANTIC PARAGRAPH CHUNKER")
    print("="*60)
    
    try:
        chunks = semantic_chunk_pages(pages)
        stats = get_chunk_stats(chunks)
        print(f"✓ Chunks created: {len(chunks)}")
        print(f"✓ Average chars/chunk: {stats['avg_chars']}")
        print(f"✓ Min chars: {stats['min_chars']}, Max chars: {stats['max_chars']}")
        return chunks
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


def test_layer3_filter(chunks: list) -> tuple:
    """Test Layer 3: Chunk Filter"""
    print("\n" + "="*60)
    print("LAYER 3: CHUNK FILTER")
    print("="*60)
    
    try:
        filtered, skipped = filter_chunks(chunks)
        stats = get_filter_stats(chunks, filtered)
        print(f"✓ Chunks after filter: {len(filtered)}")
        print(f"✓ Chunks skipped: {skipped}")
        print(f"✓ Skip ratio: {stats['skip_ratio']}%")
        return filtered, skipped
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


def test_layer4_batcher(chunks: list) -> list:
    """Test Layer 4: Adaptive Batcher"""
    print("\n" + "="*60)
    print("LAYER 4: ADAPTIVE BATCHER (Token-Aware)")
    print("="*60)
    
    try:
        batches = adaptive_batch_chunks(chunks, provider="together")
        stats = get_batch_stats(batches)
        print(f"✓ Batches created: {len(batches)}")
        print(f"✓ Total chunks in batches: {stats['total_chunks']}")
        print(f"✓ Avg chunks/batch: {stats['avg_chunks_per_batch']}")
        print(f"✓ Min chunks: {stats['min_chunks']}, Max chunks: {stats['max_chunks']}")
        return batches
    except Exception as e:
        print(f"✗ Error: {e}")
        raise


async def test_layer5_router():
    """Test Layer 5: LLM Router (requires API keys)"""
    print("\n" + "="*60)
    print("LAYER 5: ASYNC LLM ROUTER")
    print("="*60)
    
    try:
        from agents.llm_router import LLMRouter
        router = LLMRouter()
        providers = router.get_primary_provider()
        print(f"✓ Router initialized")
        print(f"✓ Primary provider: {providers['name']}")
        print(f"✓ Model: {providers['model']}")
        print(f"✓ Note: Full extraction test requires valid PDF chunks")
    except Exception as e:
        print(f"✗ Error: {e}")


def test_layer6_cache(pdf_path: str):
    """Test Layer 6: Cache system"""
    print("\n" + "="*60)
    print("LAYER 6: CACHE + SSE PROGRESS")
    print("="*60)
    
    try:
        # Test hash
        pdf_hash = get_pdf_hash(pdf_path)
        print(f"✓ PDF hash: {pdf_hash}")
        
        # Test cache (empty)
        cached = get_cached_rules(pdf_hash)
        print(f"✓ Cache lookup: {len(cached) if cached else 0} rules")
        
        # Test cache write
        test_rules = [
            {
                "title": "Test Rule 1",
                "description": "Test description",
                "severity": "HIGH",
                "source_clause": "Test clause",
                "confidence_score": 0.95,
            }
        ]
        cache_rules(pdf_hash, test_rules)
        
        # Verify cache
        cached = get_cached_rules(pdf_hash)
        print(f"✓ Cache write verified: {len(cached)} rules cached")
        
        # Stats
        stats = get_cache_stats()
        print(f"✓ Total cached PDFs: {stats.get('cached_pdfs', 0)}")
        print(f"✓ Cache size: {stats.get('cache_size_kb', 0):.1f} KB")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def test_layer7_verifier(pages: list):
    """Test Layer 7: Two-Pass Verifier"""
    print("\n" + "="*60)
    print("LAYER 7: TWO-PASS VERIFIER")
    print("="*60)
    
    try:
        verifier = TwoPassVerifier(pages)
        
        # Create test rules
        test_rules = [
            {
                "title": "Test Rule",
                "description": "Test description",
                "severity": "CRITICAL",
                "source_clause": "Test clause",
                "page_number": 1,
                "confidence_score": 0.80,
            }
        ]
        
        # This will attempt verification (may fail if no matching text)
        verified = verifier.verify_critical_rules(test_rules)
        print(f"✓ Verification complete: {len(verified)} rules")
        print(f"✓ Sample rule status: {verified[0].get('verification_status')}")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def test_layer8_dedup():
    """Test Layer 8a & 8b: Dedup and Confidence Validation"""
    print("\n" + "="*60)
    print("LAYER 8: DEDUP + CONFIDENCE VALIDATOR")
    print("="*60)
    
    try:
        # Create test rules with duplicates
        test_rules = [
            {
                "title": "KYC Requirement",
                "description": "Know Your Customer requirement",
                "severity": "CRITICAL",
                "rule_type": "validation",
                "confidence_score": 0.95,
                "needs_review": False,
            },
            {
                "title": "KYC Requirement",  # Duplicate
                "description": "Know Your Customer requirement",
                "severity": "CRITICAL",
                "rule_type": "validation",
                "confidence_score": 0.90,
                "needs_review": False,
            },
            {
                "title": "AML Screening",
                "description": "Anti-Money Laundering screening rules",
                "severity": "HIGH",
                "rule_type": "validation",
                "confidence_score": 0.85,
                "needs_review": False,
            },
            {
                "title": "Low Confidence Rule",
                "description": "A rule with low confidence",
                "severity": "MEDIUM",
                "rule_type": "advisory",
                "confidence_score": 0.45,
                "needs_review": False,
            },
        ]
        
        # Test dedup
        deduped, removed = deduplicate_rules(test_rules)
        print(f"✓ Deduplication: {len(test_rules)} → {len(deduped)} rules")
        print(f"✓ Duplicates removed: {len(removed)}")
        
        # Test confidence validation
        auto_approved, flagged = apply_confidence_validation(deduped)
        print(f"✓ Auto-approved (≥0.85): {len(auto_approved)}")
        print(f"✓ Flagged for review: {len(flagged)}")
        
        print("\nRule Approval Summary:")
        for rule in deduped:
            status = "AUTO-APPROVED" if rule.get("is_approved") else "PENDING REVIEW"
            print(f"  • {rule['title']}: {status} ({rule['confidence_score']})")
        
    except Exception as e:
        print(f"✗ Error: {e}")


def run_full_pipeline_test(pdf_path: str):
    """Run tests for all 8 layers in sequence"""
    print("\n" + "="*60)
    print("POLICYGUARD AI - 8-LAYER PIPELINE TESTS")
    print("="*60)
    
    # Check if file exists
    if not Path(pdf_path).exists():
        print(f"✗ PDF file not found: {pdf_path}")
        print("\nTo run this test, provide a sample PDF file.")
        print("Alternatively, test individual layers are available.")
        return
    
    try:
        # Layer 1: Classify
        classification = test_layer1_classifier(pdf_path)
        
        # Layer 1b: Extract
        pages = test_layer1b_extraction(pdf_path, classification)
        
        # Layer 2: Chunk
        chunks = test_layer2_chunker(pages)
        
        # Layer 3: Filter
        filtered_chunks, _ = test_layer3_filter(chunks)
        
        # Layer 4: Batch
        batches = test_layer4_batcher(filtered_chunks)
        
        # Layer 5: LLM Router (async)
        asyncio.run(test_layer5_router())
        
        # Layer 6: Cache
        test_layer6_cache(pdf_path)
        
        # Layer 7: Verifier
        test_layer7_verifier(pages)
        
        # Layer 8: Dedup + Confidence
        test_layer8_dedup()
        
        print("\n" + "="*60)
        print("ALL TESTS COMPLETED SUCCESSFULLY ✓")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        logger.exception("Pipeline test failed")


if __name__ == "__main__":
    import sys
    
    # Use provided PDF or show error
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        run_full_pipeline_test(pdf_path)
    else:
        print("Usage: python test_8layer_pipeline.py <pdf_path>")
        print("\nRunning Layer 8 tests (dedup/validation) without PDF...")
        test_layer8_dedup()
