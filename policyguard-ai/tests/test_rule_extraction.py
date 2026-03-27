# tests/test_rule_extraction.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.rule_extraction_pipeline import RuleExtractionPipeline
from core.logger import logger


def test_rule_extraction():
    logger.info("Initializing RuleExtractionPipeline...")
    pipeline = RuleExtractionPipeline()
    
    # ── Run rule extraction ────────────────────────────────────
    # This assumes the policy ingestion (tests/test_pipeline.py) has already been run
    # and chunks are available in ChromaDB.
    try:
        rules = pipeline.run()
        
        if not rules:
            logger.warning("No rules extracted. Make sure you have ingested a policy first.")
            return

        logger.info(f"Extracted {len(rules)} total rules.")

        # ── Verify first few rules ──────────────────────────────
        for i, rule in enumerate(rules[:3]):
            print(f"\n  Rule {i+1}: {rule.title}")
            print(f"  Category: {rule.category}")
            print(f"  Severity: {rule.severity}")
            print(f"  Source  : {rule.source_clause[:100]}...")

        print(f"\n✅ Rule registry updated: {len(rules)} rules processed.")
        print("Check registry/rules.json and Supabase to confirm results.")
        
    except Exception as e:
        logger.error(f"Rule extraction test failed: {e}")


if __name__ == "__main__":
    test_rule_extraction()
