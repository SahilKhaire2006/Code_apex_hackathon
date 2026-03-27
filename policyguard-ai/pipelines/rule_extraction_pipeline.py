import json
from pathlib import Path
from typing import List
from core.logger import logger
from core.config import settings
from core.schemas import Rule
from core.supabase_client import insert_rule
from core.sqlite_client import RuleRegistrySQLite
from agents.rule_extraction_agent import RuleExtractionAgent
from pipelines.policy_pipeline import PolicyPipeline


class RuleExtractionPipeline:
    """
    Orchestrates extraction of compliance rules from ingested policy chunks.
    Syncs them to registry/rules.json, SQLite, and Supabase.
    """

    def __init__(self):
        self.policy_pipeline = PolicyPipeline()
        self.extraction_agent = RuleExtractionAgent()
        self.sqlite_client = RuleRegistrySQLite()
        self.registry_path = Path(settings.rules_registry_json)
        
        # Ensure registry file exists
        if not self.registry_path.exists():
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_path, "w") as f:
                json.dump([], f)
        
        logger.info("RuleExtractionPipeline initialized")

    def run(self):
        logger.info("Starting rule extraction from all chunks")
        
        # 1. Fetch all chunks from vector store
        chunks = self.policy_pipeline.get_all_chunks()
        logger.info(f"Retrieved {len(chunks)} chunks for extraction")
        
        if not chunks:
            logger.warning("No chunks found in vector store. Run the policy ingestion first.")
            return []

        # 2. Extract rules from chunks (page-aware, batches of 5)
        all_extracted_rules: List[Rule] = []
        
        BATCH_SIZE = 5
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            combined_text = "\n\n".join([c["text"] for c in batch])
            
            # Use the page number of the first chunk in the batch for reference
            page_number = batch[0].get("metadata", {}).get("page_number", 0)
            
            rules = self.extraction_agent.extract_rules(combined_text, page_number=page_number)
            all_extracted_rules.extend(rules)
            logger.info(f"Extracted {len(rules)} rules from batch {i // BATCH_SIZE + 1} (page ~{page_number})")

        # 3. Save to Registry (JSON)
        self._sync_to_json(all_extracted_rules)
        
        # 4. Save to SQLite
        self._sync_to_sqlite(all_extracted_rules)

        # 5. Supabase sync disabled (JSON + SQLite only)
        # self._sync_to_supabase(all_extracted_rules)
        
        logger.info(f"Rule extraction complete — total {len(all_extracted_rules)} rules synced")
        return all_extracted_rules

    def _sync_to_json(self, rules: List[Rule]):
        logger.info(f"Syncing {len(rules)} rules to {self.registry_path}")
        existing_rules = []
        if self.registry_path.exists():
            with open(self.registry_path, "r") as f:
                try:
                    existing_rules = json.load(f)
                except json.JSONDecodeError:
                    existing_rules = []
        
        # Convert rules to dict
        new_rule_dicts = [r.model_dump() for r in rules]
        
        # Simple merge by rule_id or just append
        # For now, let's just replace or merge by title/description similarity?
        # Let's just combine and keep unique by rule_id
        rule_map = {r["rule_id"]: r for r in existing_rules}
        for r in new_rule_dicts:
            rule_map[r["rule_id"]] = r
            
        with open(self.registry_path, "w") as f:
            json.dump(list(rule_map.values()), f, indent=4)

    def _sync_to_sqlite(self, rules: List[Rule]):
        logger.info(f"Syncing {len(rules)} rules to SQLite")
        for rule in rules:
            self.sqlite_client.upsert_rule(rule.model_dump())

    def _sync_to_supabase(self, rules: List[Rule]):
        logger.info(f"Syncing {len(rules)} rules to Supabase")
        for rule in rules:
            try:
                insert_rule(rule.model_dump())
            except Exception as e:
                logger.error(f"Failed to sync rule {rule.title} to Supabase: {e}")
