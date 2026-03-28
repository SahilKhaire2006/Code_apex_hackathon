"""
Rule Cross-Reference Module (Jugaad Approach)
Two-pass LLM comparison of Master Direction rules vs Circular rules.
Simple, efficient, zero additional infrastructure needed.
"""

import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


CROSS_REFERENCE_SYSTEM_PROMPT = """You are a regulatory document analyst specializing in RBI compliance documents. You will be given two sets of compliance rules:

SET A: Rules extracted from the Master Direction (base document).
SET B: Rules extracted from a Circular (delta document).

Your job is to compare every rule in SET B against SET A and for each rule in SET B, determine its relationship to SET A.

For each rule in SET B, you must add two fields:

1. "status" — one of:
   "EXISTING"      → Rule in SET B is substantively identical to a rule in SET A. Same obligation, same scope, same threshold. Minor rewording is still EXISTING.
   "MODIFIED"      → Rule in SET B matches a SET A rule in topic but has a meaningful change: different threshold, different periodicity, expanded/reduced scope, new exemption, updated deadline.
   "SUPERSEDED"    → SET B rule explicitly replaces or withdraws a SET A rule.
   "CLARIFICATION" → SET B rule clarifies a SET A rule without changing its core obligation.
   "NEW"           → No matching rule exists in SET A at all.

2. "provenance_note" — a single human-readable sentence explaining the relationship."""


CROSS_REFERENCE_USER_PROMPT_TEMPLATE = """Here is SET A — Rules from the Master Direction ("{master_direction_filename}"):

{master_rules_json}

Here is SET B — Rules extracted from the Circular ("{circular_filename}"):

{circular_rules_json}

Now compare every rule in SET B against SET A.
Return ONLY a JSON array of SET B rules with two new fields added to each rule object: "status" and "provenance_note".
Do not modify any other fields. Do not return SET A.
Do not add any explanation outside the JSON array.

Example status values with provenance_note:
- EXISTING: "This rule already exists in the Master Direction and is merely referenced by this circular without change."
- MODIFIED: "Originally defined in the Master Direction; modified by this circular — [describe specific change]."
- SUPERSEDED: "This rule supersedes the Master Direction rule on [topic]. The earlier rule is no longer applicable."
- CLARIFICATION: "This is a clarification of the Master Direction rule on [topic]. The core obligation is unchanged."
- NEW: "This rule is newly introduced by this circular and does not exist in the Master Direction."

Return ONLY the JSON array with no additional text."""


def _serialize_rules_for_prompt(rules: List[Dict], max_rules: int = None) -> str:
    """
    Serialize rules for LLM prompt, stripping down to essential fields.
    
    Args:
        rules: List of rule dictionaries
        max_rules: Limit rules to reduce token count (None = all)
    
    Returns:
        JSON string of lean rule objects
    """
    if max_rules:
        rules = rules[:max_rules]
    
    lean_rules = []
    for rule in rules:
        lean = {
            "title": rule.get("title", ""),
            "description": rule.get("description", "")[:120],  # First 120 chars
            "source_clause": rule.get("source_clause", "")[:100],  # First 100 chars
            "page_number": rule.get("page_number"),
            "severity": rule.get("severity", ""),
            "id": rule.get("id", ""),
        }
        lean_rules.append(lean)
    
    return json.dumps(lean_rules, indent=2, ensure_ascii=False)


def _batch_circular_rules(circular_rules: List[Dict], batch_size: int = 20) -> List[List[Dict]]:
    """
    Split circular rules into batches for processing.
    
    Args:
        circular_rules: Rules to batch
        batch_size: Size of each batch
    
    Returns:
        List of rule batches
    """
    batches = []
    for i in range(0, len(circular_rules), batch_size):
        batches.append(circular_rules[i:i + batch_size])
    return batches


class RuleCrossReference:
    """Cross-reference circular rules against master direction rules."""
    
    def __init__(self, llm_router):
        """
        Initialize cross-reference engine.
        
        Args:
            llm_router: LLMRouter instance for LLM calls
        """
        self.router = llm_router
    
    async def compare_and_enrich(
        self,
        master_rules: List[Dict],
        circular_rules: List[Dict],
        master_direction_filename: str = "Master Direction",
        circular_filename: str = "Circular",
        tenant_id: str = "global_rbi"
    ) -> Tuple[List[Dict], Dict]:
        """
        Compare circular rules against master direction rules using two-pass LLM approach.
        
        Args:
            master_rules: Rules extracted from master direction
            circular_rules: Rules extracted from circular (to be enriched)
            master_direction_filename: Name of master direction document
            circular_filename: Name of circular document
            tenant_id: Tenant ID for logging
        
        Returns:
            Tuple of (enriched_circular_rules, statistics)
        """
        logger.info(
            f"[CrossRef] Starting comparison for {tenant_id}: "
            f"{len(master_rules)} master rules vs {len(circular_rules)} circular rules"
        )
        
        if not master_rules or not circular_rules:
            logger.warning("[CrossRef] Skipping comparison: empty master or circular rules")
            # Default all to NEW if no master rules
            for rule in circular_rules:
                rule["status"] = "NEW"
                rule["provenance_note"] = "No master direction rules available for comparison."
            return circular_rules, {
                "total_circular_rules": len(circular_rules),
                "new_rules": len(circular_rules),
                "existing_rules": 0,
                "modified_rules": 0,
                "clarification_rules": 0,
                "superseded_rules": 0,
                "error": "master_rules_empty"
            }
        
        # Serialize master rules once (reuse for all batches)
        master_rules_json = _serialize_rules_for_prompt(master_rules)
        
        # If circular rules fit in one pass, do single call
        if len(circular_rules) <= 20:
            enriched_rules = await self._single_pass_comparison(
                master_rules_json=master_rules_json,
                circular_rules=circular_rules,
                master_direction_filename=master_direction_filename,
                circular_filename=circular_filename
            )
        else:
            # Batch processing for large rule sets
            logger.info(f"[CrossRef] Large ruleset detected ({len(circular_rules)} rules); batching...")
            enriched_rules = await self._batch_comparison(
                master_rules_json=master_rules_json,
                circular_rules=circular_rules,
                master_direction_filename=master_direction_filename,
                circular_filename=circular_filename
            )
        
        # Collect statistics
        stats = self._collect_statistics(enriched_rules)
        logger.info(f"[CrossRef] Comparison complete: {stats}")
        
        return enriched_rules, stats
    
    async def _single_pass_comparison(
        self,
        master_rules_json: str,
        circular_rules: List[Dict],
        master_direction_filename: str,
        circular_filename: str
    ) -> List[Dict]:
        """
        Single LLM pass for small rule sets (≤20 rules).
        """
        circular_rules_json = _serialize_rules_for_prompt(circular_rules)
        
        user_prompt = CROSS_REFERENCE_USER_PROMPT_TEMPLATE.format(
            master_direction_filename=master_direction_filename,
            master_rules_json=master_rules_json,
            circular_filename=circular_filename,
            circular_rules_json=circular_rules_json
        )
        
        logger.debug(f"[CrossRef] Sending comparison prompt to LLM (prompt length: {len(user_prompt)} chars)")
        
        enriched_json = await self._call_llm_for_comparison(user_prompt)
        
        if not enriched_json:
            # Fallback: default all to NEW
            logger.warning("[CrossRef] LLM returned empty response; defaulting to NEW")
            for rule in circular_rules:
                rule["status"] = "NEW"
                rule["provenance_note"] = "Default: could not compare against master rules."
            return circular_rules
        
        return self._merge_enriched_rules(circular_rules, enriched_json)
    
    async def _batch_comparison(
        self,
        master_rules_json: str,
        circular_rules: List[Dict],
        master_direction_filename: str,
        circular_filename: str,
        batch_size: int = 20
    ) -> List[Dict]:
        """
        Batch processing for large rule sets.
        Process 20 rules at a time, passing all master rules each time.
        """
        batches = _batch_circular_rules(circular_rules, batch_size)
        all_enriched = []
        
        for batch_idx, batch in enumerate(batches):
            logger.info(f"[CrossRef] Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} rules)")
            
            circular_rules_json = _serialize_rules_for_prompt(batch)
            
            user_prompt = CROSS_REFERENCE_USER_PROMPT_TEMPLATE.format(
                master_direction_filename=master_direction_filename,
                master_rules_json=master_rules_json,
                circular_filename=circular_filename,
                circular_rules_json=circular_rules_json
            )
            
            enriched_json = await self._call_llm_for_comparison(user_prompt)
            
            if enriched_json:
                batch_enriched = self._merge_enriched_rules(batch, enriched_json)
                all_enriched.extend(batch_enriched)
            else:
                # Fallback for batch
                for rule in batch:
                    rule["status"] = "NEW"
                    rule["provenance_note"] = "LLM comparison failed; defaulting to NEW."
                all_enriched.extend(batch)
        
        return all_enriched
    
    async def _call_llm_for_comparison(self, user_prompt: str) -> Optional[str]:
        """
        Call LLM with comparison prompt.
        Uses Bedroq (cheap/fast) for this step, not Bedrock.
        """
        try:
            # Build batch for LLMRouter
            batch = [{
                "text": user_prompt,
                "index": 0
            }]
            
            # Call router with comparison system prompt
            logger.debug("[CrossRef] Calling LLMRouter for comparison...")
            result = await self.router.extract_all_batches_async(
                [batch],
                system_prompt=CROSS_REFERENCE_SYSTEM_PROMPT,
                progress_cb=None
            )
            
            rules = result.get("rules", [])
            if rules and len(rules) > 0:
                first_result = rules[0]
                if isinstance(first_result, str):
                    return first_result
                elif isinstance(first_result, dict):
                    return json.dumps(first_result)
            
            logger.warning("[CrossRef] LLMRouter returned empty rules")
            return None
            
        except Exception as e:
            logger.error(f"[CrossRef] LLM call failed: {e}", exc_info=True)
            return None
    
    def _merge_enriched_rules(
        self,
        original_rules: List[Dict],
        enriched_json: str
    ) -> List[Dict]:
        """
        Merge enriched data from LLM back into original rules.
        
        Args:
            original_rules: Original rule objects with all fields
            enriched_json: JSON string from LLM with status + provenance_note
        
        Returns:
            Merged rules with enriched fields
        """
        try:
            import json_repair
            enriched_data = json_repair.loads(enriched_json)
            
            if not isinstance(enriched_data, list):
                logger.warning("[CrossRef] LLM response is not a JSON array; defaulting to NEW")
                for rule in original_rules:
                    rule["status"] = "NEW"
                    rule["provenance_note"] = "Invalid LLM response; defaulting to NEW."
                return original_rules
            
            # Map enriched data back to original rules by ID or position
            merged = []
            for idx, original_rule in enumerate(original_rules):
                enriched_rule = original_rule.copy()
                
                # Try to find matching enriched entry
                enriched_entry = None
                if idx < len(enriched_data):
                    enriched_entry = enriched_data[idx]
                
                if enriched_entry and isinstance(enriched_entry, dict):
                    # Add enriched fields
                    enriched_rule["status"] = enriched_entry.get("status", "NEW")
                    enriched_rule["provenance_note"] = enriched_entry.get(
                        "provenance_note",
                        "Rule status assigned by cross-reference analysis."
                    )
                else:
                    # Fallback
                    enriched_rule["status"] = "NEW"
                    enriched_rule["provenance_note"] = "Could not map enriched data; defaulting to NEW."
                
                merged.append(enriched_rule)
            
            return merged
            
        except Exception as e:
            logger.error(f"[CrossRef] Error merging enriched rules: {e}")
            # Fallback: default all to NEW
            for rule in original_rules:
                rule["status"] = "NEW"
                rule["provenance_note"] = f"Merge error: {str(e)}"
            return original_rules
    
    def _collect_statistics(self, enriched_rules: List[Dict]) -> Dict:
        """Collect statistics about enriched rules."""
        stats = {
            "total_rules": len(enriched_rules),
            "new_rules": 0,
            "existing_rules": 0,
            "modified_rules": 0,
            "clarification_rules": 0,
            "superseded_rules": 0,
        }
        
        status_map = {
            "NEW": "new_rules",
            "EXISTING": "existing_rules",
            "MODIFIED": "modified_rules",
            "CLARIFICATION": "clarification_rules",
            "SUPERSEDED": "superseded_rules",
        }
        
        for rule in enriched_rules:
            status = rule.get("status", "NEW")
            key = status_map.get(status, "new_rules")
            stats[key] += 1
        
        return stats
