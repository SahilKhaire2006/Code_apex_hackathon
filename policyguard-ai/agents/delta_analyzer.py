"""
Delta Analyzer — FULL REWRITE (FIX 3 + FIX 6)

Implements the complete 4-step semantic comparison pipeline:
  STEP A — Vector similarity search (ChromaDB)
  STEP B — Supabase exact/fuzzy clause lookup
  STEP C — LLM comparison judgment (structured output, FIX 6 prompt)
  STEP D — Status assignment + registry action (update/insert/link)

Key changes vs old version:
  - All 5 statuses: NEW / EXISTING / MODIFIED / SUPERSEDED / CLARIFICATION
  - Similarity threshold 0.82 (cosine distance < 0.18)
  - Parallel Steps A+B
  - Dedicated LLM comparison prompt (FIX 6)
  - Proper Supabase record mutations (not just insert)
  - Skips comparison for master_direction documents
"""

import json
import asyncio
import os
from typing import List, Dict, Optional
from core.logger import logger
from core.vector_store import vector_store
from core.schemas import RuleStatus, DocumentType

# ── Similarity threshold ──────────────────────────────────────────────────
# ChromaDB uses cosine distance: 0.0 = identical, 2.0 = opposite
# distance < 0.18 ≈ similarity > 0.82 (specified in FIX 3 STEP A)
SIMILARITY_THRESHOLD_DISTANCE = 0.18


# ── LLM Comparison Prompt — FIX 6 ────────────────────────────────────────

COMPARISON_SYSTEM_PROMPT = """You are a regulatory compliance expert specializing in RBI (Reserve Bank of India) directives, Master Directions, and circulars. Your task is to determine whether a rule extracted from a new document is NEW, EXISTING, MODIFIED, SUPERSEDED, or a CLARIFICATION relative to an existing rule from the Master Direction base.

COMPARISON RULES — apply these strictly:

1. A rule is EXISTING if the legal obligation, entity scope, threshold, and enforcement mechanism are substantively identical. Minor rewording does NOT make a rule MODIFIED.

2. A rule is MODIFIED if ANY of the following changed:
   - Monetary thresholds (e.g., Rs. 40,000 → Rs. 50,000)
   - Periodicity (e.g., 6 months → 2 years)
   - Entity scope (e.g., NBFCs only → all REs)
   - New exemptions added or removed
   - Reporting deadlines changed

3. A rule is SUPERSEDED if the new document explicitly states the old rule is replaced or withdrawn (words like "replace", "supersede", "in lieu of", "withdrawn").

4. A rule is CLARIFICATION if the document uses language like "it is clarified that", "for the avoidance of doubt", "the following guidance is provided" WITHOUT changing the underlying obligation.

5. A rule is NEW only if no semantically meaningful match exists among the candidates provided.

OUTPUT — Respond ONLY with valid JSON, no other text:
{
  "matched_rule_id": "string uuid or null",
  "status": "NEW | EXISTING | MODIFIED | SUPERSEDED | CLARIFICATION",
  "confidence": <float 0.0 to 1.0>,
  "modification_summary": "concise description of what changed, or null",
  "key_delta": "specific change description (e.g. threshold Rs.40000 → Rs.50000), or null",
  "provenance_action": "introduced | referenced | modified | superseded | clarified"
}"""

COMPARISON_USER_TEMPLATE = """SOURCE DOCUMENT: {circular_name} (Type: {circular_type}, Date: {circular_date})
MASTER DIRECTION: {master_name}

NEW RULE EXTRACTED FROM CIRCULAR:
{new_rule_json}

CANDIDATE EXISTING RULES FROM MASTER DIRECTION (TOP {n_candidates}):
{existing_rules_json}

Determine the relationship. If the new rule matches one of the candidates, set matched_rule_id to that rule's ID. If no meaningful match, set matched_rule_id to null and status to NEW."""


class RuleDeltaAnalyzer:
    def __init__(self, llm_router=None):
        """
        llm_router: Optional LLMRouter instance. If None, analyzer will call
        the Groq/OpenRouter API directly using environment variables.
        """
        self.router = llm_router

    async def analyze_deltas(
        self,
        new_rules: List[Dict],
        tenant_id: str,
        document_type: str = "circular",
        source_document_name: str = "",
        source_document_date: Optional[str] = None,
        master_direction_name: str = "Master Direction",
    ) -> List[Dict]:
        """
        Main entry point.
        For master_direction docs: skip comparison, all rules → NEW.
        For circulars/amendments: run full Step A-D pipeline.
        """
        from core.schemas import DocumentType as DT

        # ── Skip comparison for base documents ────────────────────────────
        if document_type == DT.MASTER_DIRECTION.value:
            logger.info(
                f"[DeltaAnalyzer] document_type=master_direction — "
                f"marking all {len(new_rules)} rules as NEW (base document)"
            )
            for rule in new_rules:
                rule["status"] = RuleStatus.NEW.value
                rule["source_document_type"] = document_type
                rule["source_document_name"] = source_document_name
                rule["source_document_date"] = source_document_date
                rule["provenance_chain"] = [{
                    "document": source_document_name,
                    "type": document_type,
                    "date": source_document_date,
                    "action": "introduced",
                }]
            return new_rules

        logger.info(
            f"[DeltaAnalyzer] Analyzing {len(new_rules)} rules from "
            f"'{source_document_name}' (type={document_type}) for tenant '{tenant_id}'"
        )

        analyzed = []
        for rule in new_rules:
            try:
                result = await self._analyze_single_rule(
                    rule=rule,
                    tenant_id=tenant_id,
                    document_type=document_type,
                    source_document_name=source_document_name,
                    source_document_date=source_document_date,
                    master_direction_name=master_direction_name,
                )
                analyzed.append(result)
            except Exception as e:
                logger.error(f"[DeltaAnalyzer] Error analyzing rule '{rule.get('title')}': {e}")
                rule["status"] = RuleStatus.NEW.value
                analyzed.append(rule)

        # Summary stats
        status_counts = {}
        for r in analyzed:
            s = r.get("status", "?")
            status_counts[s] = status_counts.get(s, 0) + 1
        logger.info(f"[DeltaAnalyzer] Analysis complete — {status_counts}")
        return analyzed

    async def _analyze_single_rule(
        self,
        rule: Dict,
        tenant_id: str,
        document_type: str,
        source_document_name: str,
        source_document_date: Optional[str],
        master_direction_name: str,
    ) -> Dict:
        """Steps A-D for a single rule."""
        query = f"{rule.get('title', '')} {rule.get('description', '')} {rule.get('source_clause', '')}"

        # ── STEP A + B (parallel) ─────────────────────────────────────────
        vector_matches, clause_matches = await asyncio.gather(
            self._step_a_vector_search(query, tenant_id),
            self._step_b_clause_search(rule.get("source_clause", "")),
        )

        # Merge and deduplicate candidates by rule id
        candidates = _merge_candidates(vector_matches, clause_matches)
        logger.debug(
            f"[DeltaAnalyzer] Rule '{rule.get('title')}': "
            f"{len(vector_matches)} vector + {len(clause_matches)} clause → "
            f"{len(candidates)} unique candidates"
        )

        if not candidates:
            # Definitely NEW
            rule["status"] = RuleStatus.NEW.value
            rule["source_document_name"] = source_document_name
            rule["source_document_type"] = document_type
            rule["source_document_date"] = source_document_date
            rule["provenance_chain"] = [{
                "document": source_document_name,
                "type": document_type,
                "date": source_document_date,
                "action": "introduced",
            }]
            logger.debug(f"[DeltaAnalyzer] Rule '{rule.get('title')}' → NEW (no candidates)")
            return rule

        # ── STEP C — LLM Comparison Judgment ─────────────────────────────
        judgment = await self._step_c_llm_judgment(
            new_rule=rule,
            candidates=candidates[:3],    # top-3 only
            circular_name=source_document_name,
            circular_type=document_type,
            circular_date=source_document_date or "unknown",
            master_name=master_direction_name,
        )

        # ── STEP D — Status Assignment & Record Action ────────────────────
        rule = await self._step_d_record_action(
            rule=rule,
            judgment=judgment,
            document_type=document_type,
            source_document_name=source_document_name,
            source_document_date=source_document_date,
            candidates=candidates,
        )

        return rule

    # ── STEP A: Vector similarity search ─────────────────────────────────

    async def _step_a_vector_search(self, query: str, tenant_id: str) -> List[Dict]:
        """Search ChromaDB for semantically similar rules (master_direction base)."""
        try:
            loop = asyncio.get_event_loop()
            matches = await loop.run_in_executor(
                None,
                lambda: vector_store.search_similar_rules(query, tenant_id=tenant_id, limit=5),
            )
            # Filter by similarity threshold: distance < SIMILARITY_THRESHOLD_DISTANCE
            valid = [m for m in matches if m.get("distance", 1.0) < SIMILARITY_THRESHOLD_DISTANCE]
            logger.debug(f"[DeltaAnalyzer] Step A: {len(valid)}/{len(matches)} matches above threshold")
            return valid
        except Exception as e:
            logger.warning(f"[DeltaAnalyzer] Step A vector search failed: {e}")
            return []

    # ── STEP B: Supabase clause lookup ────────────────────────────────────

    async def _step_b_clause_search(self, source_clause: str) -> List[Dict]:
        """ILIKE search against rules_registry.source_clause in Supabase."""
        try:
            from core.supabase_client import search_rules_by_clause, _supabase_available
            if not _supabase_available():
                return []
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: search_rules_by_clause(source_clause, limit=3),
            )
            # Transform Supabase rows into candidate format
            candidates = []
            for row in results:
                candidates.append({
                    "id": row.get("rule_id"),
                    "document": json.dumps({
                        "title": row.get("title"),
                        "description": row.get("description"),
                        "source_clause": row.get("source_clause"),
                        "source_document_name": row.get("source_document_name"),
                        "source_document_type": row.get("source_document_type"),
                    }),
                    "metadata": {
                        "title": row.get("title"),
                        "source_document_type": row.get("source_document_type"),
                        "severity": row.get("severity"),
                    },
                    "distance": 0.1,    # Clause match gets high boost
                    "_full_row": row,
                })
            return candidates
        except Exception as e:
            logger.warning(f"[DeltaAnalyzer] Step B clause search failed: {e}")
            return []

    # ── STEP C: LLM comparison judgment ──────────────────────────────────

    async def _step_c_llm_judgment(
        self,
        new_rule: Dict,
        candidates: List[Dict],
        circular_name: str,
        circular_type: str,
        circular_date: str,
        master_name: str,
    ) -> Dict:
        """Send comparison pair to LLM, parse structured judgment."""
        # Build simplified candidate objects for the prompt
        existing_summaries = []
        for c in candidates:
            try:
                # Prefer full row from Supabase; fall back to vector metadata
                full = c.get("_full_row", {})
                existing_summaries.append({
                    "id": c.get("id"),
                    "title": full.get("title") or c["metadata"].get("title", ""),
                    "description": full.get("description", ""),
                    "source_clause": full.get("source_clause", ""),
                    "source_document_name": full.get("source_document_name", master_name),
                    "source_document_type": full.get("source_document_type", "master_direction"),
                    "severity": full.get("severity", ""),
                    "condition_value": full.get("condition_value"),
                    "condition_unit": full.get("condition_unit"),
                })
            except Exception:
                existing_summaries.append({"id": c.get("id"), "document": c.get("document", "")})

        new_rule_summary = {
            "title": new_rule.get("title"),
            "description": new_rule.get("description"),
            "source_clause": new_rule.get("source_clause"),
            "severity": new_rule.get("severity"),
            "condition_value": new_rule.get("condition_value"),
            "condition_unit": new_rule.get("condition_unit"),
            "category": new_rule.get("category"),
        }

        user_prompt = COMPARISON_USER_TEMPLATE.format(
            circular_name=circular_name,
            circular_type=circular_type,
            circular_date=circular_date,
            master_name=master_name,
            new_rule_json=json.dumps(new_rule_summary, indent=2),
            existing_rules_json=json.dumps(existing_summaries, indent=2),
            n_candidates=len(existing_summaries),
        )

        try:
            import aiohttp
            import json_repair

            api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
            if "gsk_" in api_key:
                url = "https://api.groq.com/openai/v1/chat/completions"
                model = "llama-3.3-70b-versatile"
            else:
                url = "https://openrouter.ai/api/v1/chat/completions"
                model = "meta-llama/llama-3.3-70b-instruct"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": COMPARISON_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "max_tokens": 512,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw = data["choices"][0]["message"]["content"]
                        result = json_repair.loads(raw)
                        logger.debug(
                            f"[DeltaAnalyzer] Step C judgment: "
                            f"status={result.get('status')}, "
                            f"confidence={result.get('confidence'):.2f}, "
                            f"matched_id={result.get('matched_rule_id')}"
                        )
                        return result
                    else:
                        logger.error(f"[DeltaAnalyzer] Step C LLM error HTTP {resp.status}")
                        return _judgment_new()
        except Exception as e:
            logger.error(f"[DeltaAnalyzer] Step C LLM call failed: {e}")
            return _judgment_new()

    # ── STEP D: Status assignment + registry action ───────────────────────

    async def _step_d_record_action(
        self,
        rule: Dict,
        judgment: Dict,
        document_type: str,
        source_document_name: str,
        source_document_date: Optional[str],
        candidates: List[Dict],
    ) -> Dict:
        """
        Apply judgment to the rule and mutate Supabase records accordingly.
        """
        status = judgment.get("status", RuleStatus.NEW.value)
        matched_id = judgment.get("matched_rule_id")
        mod_summary = judgment.get("modification_summary")
        provenance_action = judgment.get("provenance_action", "referenced")

        provenance_entry = {
            "document": source_document_name,
            "type": document_type,
            "date": source_document_date,
            "action": provenance_action,
        }

        rule["status"] = status
        rule["source_document_name"] = source_document_name
        rule["source_document_type"] = document_type
        rule["source_document_date"] = source_document_date

        try:
            from core.supabase_client import (
                update_rule_provenance, update_rule_in_registry,
                fetch_rule_by_id, _supabase_available,
            )
            supabase_ok = _supabase_available()
        except Exception:
            supabase_ok = False

        if status == RuleStatus.EXISTING.value:
            # ── Do NOT insert duplicate. Update provenance only. ─────────
            rule["supersedes_rule_id"] = None
            rule["modification_summary"] = None
            rule["provenance_chain"] = [provenance_entry]
            if supabase_ok and matched_id:
                update_rule_provenance(matched_id, provenance_entry)
            logger.info(
                f"[DeltaAnalyzer] Rule '{rule.get('title')}' → EXISTING "
                f"(matches {matched_id})"
            )

        elif status == RuleStatus.MODIFIED.value:
            # ── Update existing record in Supabase ───────────────────────
            rule["modification_summary"] = mod_summary
            rule["last_modified_by"] = source_document_name
            rule["provenance_chain"] = [provenance_entry]
            if supabase_ok and matched_id:
                # Save old version to rule_history
                old_rule = fetch_rule_by_id(matched_id)
                old_history = old_rule.get("rule_history", []) if old_rule else []
                if isinstance(old_history, str):
                    old_history = json.loads(old_history)
                old_history.append(old_rule)

                update_rule_in_registry(matched_id, {
                    "status": RuleStatus.MODIFIED.value,
                    "last_modified_by": source_document_name,
                    "modification_summary": mod_summary,
                    "rule_history": old_history,
                })
                update_rule_provenance(
                    matched_id, provenance_entry,
                    extra_updates={"modification_summary": mod_summary}
                )
            logger.info(
                f"[DeltaAnalyzer] Rule '{rule.get('title')}' → MODIFIED "
                f"(delta: {judgment.get('key_delta')})"
            )

        elif status == RuleStatus.SUPERSEDED.value:
            # ── Insert new, mark old as SUPERSEDED ───────────────────────
            rule["supersedes_rule_id"] = matched_id
            rule["provenance_chain"] = [provenance_entry]
            if supabase_ok and matched_id:
                update_rule_in_registry(matched_id, {"status": RuleStatus.SUPERSEDED.value})
                update_rule_provenance(matched_id, {**provenance_entry, "action": "superseded"})
            logger.info(
                f"[DeltaAnalyzer] Rule '{rule.get('title')}' → SUPERSEDED (old id={matched_id})"
            )

        elif status == RuleStatus.CLARIFICATION.value:
            # ── Insert linked record ─────────────────────────────────────
            rule["parent_rule_id"] = matched_id
            rule["provenance_chain"] = [provenance_entry]
            if supabase_ok and matched_id:
                update_rule_provenance(matched_id, {**provenance_entry, "action": "clarified"})
            logger.info(
                f"[DeltaAnalyzer] Rule '{rule.get('title')}' → CLARIFICATION "
                f"(parent={matched_id})"
            )

        else:
            # NEW — fresh insert
            rule["status"] = RuleStatus.NEW.value
            rule["provenance_chain"] = [{
                "document": source_document_name,
                "type": document_type,
                "date": source_document_date,
                "action": "introduced",
            }]
            logger.info(f"[DeltaAnalyzer] Rule '{rule.get('title')}' → NEW")

        return rule


# ── Helpers ───────────────────────────────────────────────────────────────

def _judgment_new() -> Dict:
    """Default fallback judgment when LLM call fails."""
    return {
        "matched_rule_id": None,
        "status": RuleStatus.NEW.value,
        "confidence": 0.5,
        "modification_summary": None,
        "key_delta": None,
        "provenance_action": "introduced",
    }


def _merge_candidates(vector_matches: List[Dict], clause_matches: List[Dict]) -> List[Dict]:
    """Merge and deduplicate by rule id, prefer lowest distance."""
    seen = {}
    for m in [*vector_matches, *clause_matches]:
        rid = m.get("id")
        if not rid:
            continue
        if rid not in seen or m.get("distance", 1.0) < seen[rid].get("distance", 1.0):
            seen[rid] = m
    return list(seen.values())
