"""
Layer 9: Delta Analyzer
Integrates with ChromaDB and LLM Router to detect modifications.
"""

import json
from typing import List, Dict
from core.logger import logger
from core.vector_store import vector_store

DELTA_PROMPT = """You are an expert regulatory compliance analyst.
A new circular has been issued, and we found a potential modification of an old Master Direction rule.

NEW RULE EXTRACTED FROM RECENT CIRCULAR:
{new_rule_json}

HISTORICAL ACTIVE RULE(S) FROM VECTOR DB THAT IT MIGHT MODIFY:
{historical_rules_json}

Compare the New Rule to the Historical Rules. Check if the New Rule modifies, updates, or supersedes any of the Historical Rules.
- If it clearly updates/modifies one of the historical rules (e.g., changes a threshold, expands a definition), output status = "MODIFIED".
- If it is completely unrelated to the provided historical rules, output status = "NEW".

Answer with ONLY this JSON format:
{{
  "status": "MODIFIED" or "NEW",
  "supersedes_rule_id": "id of the old rule if MODIFIED, else null",
  "change_summary": "A 1-sentence summary of what exactly changed, else null"
}}"""

class RuleDeltaAnalyzer:
    def __init__(self, llm_router):
        """Pass the initialized LLMRouter instance to use its providers"""
        self.router = llm_router

    async def analyze_deltas(self, new_rules: List[Dict], tenant_id: str) -> List[Dict]:
        """
        Takes newly extracted rules and checks if they modify existing rules.
        """
        logger.info(f"[DeltaAnalyzer] Analyzing {len(new_rules)} rules for tenant {tenant_id}...")
        analyzed_rules = []

        for i, rule in enumerate(new_rules):
            # 1. Search for similar historical rules
            query = f"{rule.get('title', '')} {rule.get('description', '')}"
            matches = vector_store.search_similar_rules(query, tenant_id=tenant_id, limit=2)
            
            # Filter matches to only include high similarity (distance < 0.4 roughly in cosine)
            valid_matches = [m for m in matches if m.get("distance", 1.0) < 0.6]

            if not valid_matches:
                # No historically related rule, it's definitely new
                rule["status"] = "NEW"
                rule["change_summary"] = "New addition in this circular."
                analyzed_rules.append(rule)
                continue

            # 2. Build prompt for LLM comparison
            historical_data = []
            for match in valid_matches:
                historical_data.append({
                    "id": match["id"],
                    "document": match["document"],
                    "metadata": match["metadata"]
                })

            prompt = DELTA_PROMPT.format(
                new_rule_json=json.dumps(rule, indent=2),
                historical_rules_json=json.dumps(historical_data, indent=2)
            )

            # 3. Ask LLM to compare
            try:
                import os
                import aiohttp
                import json_repair
                
                logger.debug(f"[DeltaAnalyzer] Comparing rule '{rule.get('title')}' against {len(historical_data)} historical rules...")
                
                api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY")
                url = "https://api.groq.com/openai/v1/chat/completions" if "gsk_" in (api_key or "") else "https://openrouter.ai/api/v1/chat/completions"
                model = "llama-3.3-70b-versatile" if "gsk_" in (api_key or "") else "meta-llama/llama-3.3-70b-instruct"
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            raw_content = data['choices'][0]['message']['content']
                            result = json_repair.loads(raw_content)
                            
                            rule["status"] = result.get("status", "NEW")
                            if rule["status"] == "MODIFIED":
                                rule["supersedes_rule_id"] = result.get("supersedes_rule_id")
                                rule["change_summary"] = result.get("change_summary")
                        else:
                            logger.error(f"[DeltaAnalyzer] Error {resp.status} from LLM")
                            rule["status"] = "NEW"
                            
            except Exception as e:
                logger.error(f"[DeltaAnalyzer] LLM error for rule {rule['id']}: {e}")
                rule["status"] = "NEW"
            
            analyzed_rules.append(rule)
            
        return analyzed_rules
