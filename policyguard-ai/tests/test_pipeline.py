# tests/test_pipeline.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.policy_pipeline import PolicyPipeline
from core.logger import logger

def test_policy_pipeline():
    pipeline = PolicyPipeline()

    # ── Run ingestion ──────────────────────────────────────────
    result = pipeline.run("data/policy_pdfs/aml_policy.pdf")

    logger.info(f"Session ID   : {result.session_id}")
    logger.info(f"File         : {result.filename}")
    logger.info(f"Pages        : {result.total_pages}")
    logger.info(f"Chunks       : {result.total_chunks}")
    logger.info(f"Status       : {result.status}")

    # ── Test retrieval ─────────────────────────────────────────
    logger.info("Testing semantic retrieval...")
    results = pipeline.query("transaction amount threshold suspicious activity", n_results=3)

    for i, r in enumerate(results):
        print(f"\n  Result {i+1} — Score: {r['relevance_score']}")
        print(f"  Page     : {r['metadata']['page_number']}")
        print(f"  Section  : {r['metadata']['section_title']}")
        print(f"  Text     : {r['text'][:120]}...")

    # ── Verify Supabase session ────────────────────────────────
    from core.supabase_client import get_supabase
    client = get_supabase()
    session = client.table("ingestion_sessions") \
        .select("*").eq("id", result.session_id).execute()
    print(f"\n  Supabase Session: {session.data[0]}")

if __name__ == "__main__":
    test_policy_pipeline()